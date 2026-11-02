from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from main import create_app
from package.auth.discord import DiscordError, DiscordUser
from package.browser.policies import UrlNotAllowed, check_url
from package.browser.runtime import FakeRuntime
from package.config import Settings

HOSTS = {
    "example.com": ["93.184.216.34"],
    "internal.example": ["10.0.0.5"],
    "localhost": ["127.0.0.1", "::1"],
    "rebind.example": ["93.184.216.34", "192.168.1.10"],
}


async def fake_resolver(host: str, port: int) -> list[str]:
    if host in HOSTS:
        return HOSTS[host]
    raise UrlNotAllowed(f"cannot resolve host: {host}")


async def fake_check(url: str) -> None:
    await check_url(url, resolver=fake_resolver)


class FakeDiscord:
    """code をそのままDiscord IDとして扱う。code='bad' はトークン交換の失敗。"""

    configured = True

    def __init__(self) -> None:
        self.revoked: list[str] = []

    def authorize_url(self, state: str) -> str:
        return f"https://discord.test/authorize?state={state}"

    async def exchange_code(self, code: str) -> str:
        if code == "bad":
            raise DiscordError("token exchange failed")
        return f"token-{code}"

    async def fetch_user(self, access_token: str) -> DiscordUser:
        discord_id = access_token.removeprefix("token-")
        return DiscordUser(discord_id, f"user{discord_id}", None)

    async def revoke_token(self, access_token: str) -> None:
        self.revoked.append(access_token)

    async def aclose(self) -> None:
        return None


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@dataclass
class Env:
    app: FastAPI
    settings: Settings
    runtime: FakeRuntime
    discord: FakeDiscord
    clock: Clock

    @property
    def sessions(self) -> Any:
        return self.app.state.container.sessions

    @property
    def repo(self) -> Any:
        return self.app.state.container.repo


EnvFactory = Callable[..., Env]


@pytest.fixture
def env_factory(tmp_path: Path) -> EnvFactory:
    def make(**overrides: Any) -> Env:
        values: dict[str, Any] = {
            "app_secret_key": "k" * 40,
            "discord_client_id": "cid",
            "discord_client_secret": "secret",
            "browser_allowed_hosts": "example.com",
            "database_path": str(tmp_path / "app.db"),
            "browser_runtime": "fake",
            "novnc_dir": str(tmp_path / "no-novnc"),
            "frontend_dir": str(tmp_path / "no-frontend"),
            "sweep_interval_seconds": 3600,
        }
        values.update(overrides)
        settings = Settings(_env_file=None, **values)  # pyright: ignore[reportCallIssue]
        runtime, discord, clock = FakeRuntime(), FakeDiscord(), Clock()
        app = create_app(
            settings, runtime=runtime, discord=discord, clock=clock, url_checker=fake_check
        )
        return Env(app, settings, runtime, discord, clock)

    return make


@pytest.fixture
def env(env_factory: EnvFactory) -> Env:
    return env_factory()


@pytest.fixture
def client(env: Env) -> Iterator[TestClient]:
    with TestClient(env.app) as c:
        yield c


def login(client: TestClient, discord_id: str = "1001") -> str:
    """OAuthフロー全体を通してログインし、CSRFトークンを返す。"""
    client.cookies.clear()
    r = client.get("/auth/discord", follow_redirects=False)
    assert r.status_code == 302, r.text
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    r = client.get(
        "/auth/callback", params={"code": discord_id, "state": state}, follow_redirects=False
    )
    assert r.status_code == 302, r.text
    assert r.headers["location"] == "/browser.html"
    me = client.get("/api/me")
    assert me.status_code == 200
    return str(me.json()["csrf_token"])


def csrf(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def run_async(client: TestClient, func: Callable[..., Any], *args: Any) -> Any:
    """TestClientのイベントループ上で非同期関数(sweepなど)を実行する。"""
    assert client.portal is not None
    return client.portal.call(func, *args)
