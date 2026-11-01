from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from starlette.requests import HTTPConnection

from package.auth.oauth import SESSION_COOKIE
from package.database.models import User
from package.state import container


@dataclass(frozen=True, slots=True)
class AuthContext:
    user: User
    csrf_token: str


def authenticate(conn: HTTPConnection) -> AuthContext | None:
    """HTTP/WebSocket共通: Cookieから認証済みユーザーを復元する。"""
    c = container(conn)
    token = conn.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    payload = c.codec.loads(token)
    if payload is None:
        return None
    user = c.users.get(payload.uid)
    # 許可リストから外されたユーザーは、既存Cookieがあっても即座に拒否する
    if user is None or not c.users.is_allowed(user.discord_id):
        return None
    return AuthContext(user, payload.csrf)


def require_user(request: Request) -> AuthContext:
    ctx = authenticate(request)
    if ctx is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return ctx


CurrentUser = Annotated[AuthContext, Depends(require_user)]
