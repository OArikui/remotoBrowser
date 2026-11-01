"""ログインセッションCookieの署名と、OAuth2 state の生成。"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from itsdangerous import BadSignature, URLSafeTimedSerializer

SESSION_COOKIE = "rb_session"
STATE_COOKIE = "rb_oauth_state"


@dataclass(frozen=True, slots=True)
class SessionPayload:
    uid: int
    csrf: str


def new_state() -> str:
    return secrets.token_urlsafe(32)


class SessionCodec:
    """Cookieの中身は「内部ユーザーID」と「CSRFトークン」だけ。Discordのトークンは入れない。"""

    def __init__(self, secret: str, max_age: int) -> None:
        self._serializer = URLSafeTimedSerializer(secret, salt="rb-session")
        self._max_age = max_age

    def issue(self, user_id: int) -> str:
        return self._serializer.dumps({"uid": user_id, "csrf": secrets.token_urlsafe(24)})

    def loads(self, token: str) -> SessionPayload | None:
        try:
            data: Any = self._serializer.loads(token, max_age=self._max_age)
        except BadSignature:  # 期限切れ(SignatureExpired)も含む
            return None
        if not isinstance(data, dict):
            return None
        uid = data.get("uid")
        csrf = data.get("csrf")
        if not isinstance(uid, int) or not isinstance(csrf, str):
            return None
        return SessionPayload(uid, csrf)
