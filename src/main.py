"""アプリケーションの組み立て。起動は `python run.py` か
`uvicorn main:create_app --factory`。"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from package import __version__
from package.api import auth as auth_api
from package.api import browser as browser_api
from package.api import health as health_api
from package.api import sessions as sessions_api
from package.api import users as users_api
from package.auth.discord import DiscordClient, DiscordProvider
from package.auth.oauth import SessionCodec
from package.browser.lifecycle import ProcessRuntime
from package.browser.manager import BrowserManager
from package.browser.policies import (
    UrlChecker,
    UrlNotAllowed,
    build_url_checker,
    normalize_hostname,
)
from package.browser.runtime import BrowserRuntime, FakeRuntime
from package.config import Settings
from package.database.connection import Database
from package.database.repository import Repository
from package.security.middleware import RateLimiter, SecurityHeadersMiddleware
from package.services.browser_service import BrowserService
from package.services.user_service import UserService
from package.sessions.cleanup import run_cleanup_loop
from package.sessions.manager import SessionManager
from package.state import AppContainer
from package.utils import configure_logging, utcnow

log = logging.getLogger("rb.app")


def _combine_url_checkers(settings: Settings, resolver_checker: UrlChecker) -> UrlChecker:
    """テスト用チェッカーを許可リスト検査の後段に接続する。"""
    allowed_hosts = settings.browser_hosts

    async def checker(url: str) -> None:
        try:
            host = urlsplit(url).hostname
        except ValueError as exc:
            raise UrlNotAllowed("invalid URL") from exc
        if host is None:
            raise UrlNotAllowed("URL has no host")
        try:
            normalized = normalize_hostname(host)
        except ValueError as exc:
            raise UrlNotAllowed("destination hostname is not allowed") from exc
        if normalized not in allowed_hosts:
            raise UrlNotAllowed("destination host is not in BROWSER_ALLOWED_HOSTS")
        await resolver_checker(url)

    return checker


def create_app(
    settings: Settings | None = None,
    *,
    runtime: BrowserRuntime | None = None,
    discord: DiscordProvider | None = None,
    clock: Callable[[], datetime] = utcnow,
    url_checker: UrlChecker | None = None,
) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)
    # アプリ入口とChromiumリクエストの両方で同一の完全一致ホスト制限を適用する。
    checker = (
        build_url_checker(settings.browser_hosts)
        if url_checker is None
        else _combine_url_checkers(settings, url_checker)
    )

    db = Database(settings.database_path)
    db.init()
    repo = Repository(db)

    if runtime is None:
        if settings.browser_runtime == "fake":
            runtime = FakeRuntime()
        else:
            runtime = ProcessRuntime(
                width=settings.screen_width,
                height=settings.screen_height,
                url_checker=checker,
            )
    browser = BrowserManager(runtime, settings.default_start_url, checker)
    sessions = SessionManager(repo, browser, settings, clock)
    discord_client = discord or DiscordClient(
        settings.discord_client_id, settings.discord_client_secret, settings.redirect_uri
    )

    app_container = AppContainer(
        settings=settings,
        repo=repo,
        users=UserService(repo, settings.allowed_ids, clock),
        sessions=sessions,
        browser_service=BrowserService(sessions, repo, settings),
        discord=discord_client,
        codec=SessionCodec(settings.app_secret_key, settings.login_ttl_seconds),
        login_limiter=RateLimiter(settings.rate_limit_login_per_minute),
        start_limiter=RateLimiter(settings.rate_limit_start_per_minute),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await sessions.reconcile_on_startup()
        sweeper = asyncio.create_task(run_cleanup_loop(sessions, settings.sweep_interval_seconds))
        log.info("remote-browser %s started (runtime=%s)", __version__, settings.browser_runtime)
        try:
            yield
        finally:
            sweeper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sweeper
            await sessions.shutdown()
            await browser.shutdown()
            await discord_client.aclose()

    docs = "/docs" if settings.enable_docs else None
    app = FastAPI(
        title="Remote Browser",
        version=__version__,
        lifespan=lifespan,
        docs_url=docs,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.enable_docs else None,
    )
    app.state.container = app_container
    app.add_middleware(SecurityHeadersMiddleware, ws_origin=settings.ws_origin)

    for module in (health_api, auth_api, users_api, browser_api, sessions_api):
        app.include_router(module.router)

    # noVNCクライアント(Debian系の novnc パッケージ)とフロントエンド。"/" のマウントは必ず最後。
    novnc = Path(settings.novnc_dir)
    if novnc.is_dir():
        app.mount("/novnc", StaticFiles(directory=novnc), name="novnc")
    frontend = Path(settings.frontend_dir)
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")

    return app
