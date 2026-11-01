from __future__ import annotations

import logging
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from package.auth.discord import DiscordError
from package.auth.oauth import SESSION_COOKIE, STATE_COOKIE, new_state
from package.security.csrf import CsrfUser
from package.services.user_service import NotAllowedError
from package.state import client_key, container

log = logging.getLogger("rb.auth")

router = APIRouter(prefix="/auth", tags=["auth"])


def _limit_login(request: Request) -> None:
    if not container(request).login_limiter.hit(client_key(request)):
        raise HTTPException(status_code=429, detail="too many requests")


@router.get("/discord")
async def discord_login(request: Request, _: Annotated[None, Depends(_limit_login)]) -> Response:
    c = container(request)
    if not c.discord.configured:
        raise HTTPException(status_code=503, detail="Discord OAuth is not configured")
    state = new_state()
    response = RedirectResponse(c.discord.authorize_url(state), status_code=302)
    response.set_cookie(
        STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=c.settings.cookie_secure,
        samesite="lax",
        path="/auth",
    )
    return response


def _login_redirect(error: str, secure: bool) -> RedirectResponse:
    response = RedirectResponse(f"/login.html?error={error}", status_code=302)
    response.delete_cookie(STATE_COOKIE, path="/auth", secure=secure, httponly=True, samesite="lax")
    return response


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    c = container(request)
    secure = c.settings.cookie_secure
    expected = request.cookies.get(STATE_COOKIE)

    if error:  # ユーザーがDiscord上で拒否した等
        return _login_redirect("denied", secure)
    if (
        not code
        or not state
        or not expected
        or not secrets.compare_digest(state.encode(), expected.encode())
    ):
        log.warning("oauth callback with missing/invalid state")
        raise HTTPException(status_code=400, detail="invalid oauth state")

    access_token: str | None = None
    try:
        access_token = await c.discord.exchange_code(code)
        discord_user = await c.discord.fetch_user(access_token)
    except DiscordError:
        log.warning("discord oauth failed", exc_info=True)
        return _login_redirect("discord", secure)
    finally:
        if access_token:
            await c.discord.revoke_token(access_token)  # 以後は使わないので失効させる

    try:
        user = c.users.login(discord_user)
    except NotAllowedError:
        return _login_redirect("not_allowed", secure)

    response = RedirectResponse("/browser.html", status_code=302)
    response.delete_cookie(STATE_COOKIE, path="/auth", secure=secure, httponly=True, samesite="lax")
    response.set_cookie(
        SESSION_COOKIE,
        c.codec.issue(user.id),
        max_age=c.settings.login_ttl_seconds,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/logout")
async def logout(request: Request, ctx: CsrfUser) -> Response:
    c = container(request)
    await c.browser_service.stop(ctx.user)  # ログアウト時はブラウザも破棄する
    response = JSONResponse({"ok": True})
    response.delete_cookie(
        SESSION_COOKIE, path="/", secure=c.settings.cookie_secure, httponly=True, samesite="lax"
    )
    return response
