"""アプリ全体で共有するオブジェクトの入れ物。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from starlette.requests import HTTPConnection

from package.auth.discord import DiscordProvider
from package.auth.oauth import SessionCodec
from package.config import Settings
from package.database.repository import Repository
from package.security.middleware import RateLimiter
from package.services.browser_service import BrowserService
from package.services.user_service import UserService
from package.sessions.manager import SessionManager


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    repo: Repository
    users: UserService
    sessions: SessionManager
    browser_service: BrowserService
    discord: DiscordProvider
    codec: SessionCodec
    login_limiter: RateLimiter
    start_limiter: RateLimiter


def container(conn: HTTPConnection) -> AppContainer:
    return cast(AppContainer, conn.app.state.container)


def client_key(conn: HTTPConnection) -> str:
    return conn.client.host if conn.client else "unknown"
