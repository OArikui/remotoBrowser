"""Discord OAuth2(Authorization Code Grant, scope=identify)。"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import httpx

log = logging.getLogger("rb.auth")

AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
TOKEN_URL = "https://discord.com/api/oauth2/token"
REVOKE_URL = "https://discord.com/api/oauth2/token/revoke"
ME_URL = "https://discord.com/api/users/@me"


class DiscordError(Exception):
    """Discordとの通信・応答の失敗。"""


@dataclass(frozen=True, slots=True)
class DiscordUser:
    id: str
    username: str
    avatar: str | None


class DiscordProvider(Protocol):
    @property
    def configured(self) -> bool: ...

    def authorize_url(self, state: str) -> str: ...

    async def exchange_code(self, code: str) -> str: ...

    async def fetch_user(self, access_token: str) -> DiscordUser: ...

    async def revoke_token(self, access_token: str) -> None: ...

    async def aclose(self) -> None: ...


class DiscordClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._http = http or httpx.AsyncClient(timeout=10.0)

    @property
    def configured(self) -> bool:
        return bool(self._client_id and self._client_secret)

    def authorize_url(self, state: str) -> str:
        query = urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": "identify",
                "state": state,
                "prompt": "none",
            }
        )
        return f"{AUTHORIZE_URL}?{query}"

    async def exchange_code(self, code: str) -> str:
        try:
            resp = await self._http.post(
                TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise DiscordError("token endpoint unreachable") from exc
        if resp.status_code != 200:
            raise DiscordError(f"token exchange failed (HTTP {resp.status_code})")
        token = resp.json().get("access_token")
        if not isinstance(token, str) or not token:
            raise DiscordError("token response had no access_token")
        return token

    async def fetch_user(self, access_token: str) -> DiscordUser:
        try:
            resp = await self._http.get(ME_URL, headers={"Authorization": f"Bearer {access_token}"})
        except httpx.HTTPError as exc:
            raise DiscordError("user endpoint unreachable") from exc
        if resp.status_code != 200:
            raise DiscordError(f"fetching user failed (HTTP {resp.status_code})")
        data = resp.json()
        user_id = data.get("id")
        if not isinstance(user_id, str) or not user_id:
            raise DiscordError("user response had no id")
        name = data.get("global_name") or data.get("username") or user_id
        avatar = data.get("avatar")
        return DiscordUser(user_id, str(name), avatar if isinstance(avatar, str) else None)

    async def revoke_token(self, access_token: str) -> None:
        """認証後は不要なアクセストークンを失効させる(失敗しても無視)。"""
        with contextlib.suppress(httpx.HTTPError):
            await self._http.post(
                REVOKE_URL,
                data={
                    "token": access_token,
                    "token_type_hint": "access_token",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )

    async def aclose(self) -> None:
        await self._http.aclose()
