from __future__ import annotations

from package.auth.oauth import SessionCodec
from package.browser.lifecycle import RequestGuard
from package.security.middleware import RateLimiter
from tests.conftest import fake_check


def test_codec_roundtrip_and_tamper() -> None:
    codec = SessionCodec("s" * 40, max_age=60)
    token = codec.issue(7)
    payload = codec.loads(token)
    assert payload is not None
    assert payload.uid == 7
    assert payload.csrf
    assert codec.loads(token + "x") is None
    assert SessionCodec("other-secret-" + "z" * 30, 60).loads(token) is None


def test_codec_expired() -> None:
    codec = SessionCodec("s" * 40, max_age=-1)
    assert codec.loads(codec.issue(1)) is None


def test_rate_limiter_window() -> None:
    now = [0.0]
    limiter = RateLimiter(2, window_seconds=60, clock=lambda: now[0])
    assert limiter.hit("a")
    assert limiter.hit("a")
    assert not limiter.hit("a")
    assert limiter.hit("b")  # キーごとに独立
    now[0] = 61
    assert limiter.hit("a")


async def test_request_guard() -> None:
    guard = RequestGuard(fake_check)
    assert await guard.allows("https://example.com/a.js")
    assert await guard.allows("data:text/plain,hello")
    assert not await guard.allows("http://internal.example/admin")
    assert not await guard.allows("http://localhost:9999/")
    assert not await guard.allows("file:///etc/passwd")
    assert not await guard.allows("chrome://settings")
    assert await guard.allows_websocket("wss://example.com/socket")
    assert not await guard.allows_websocket("wss://internal.example/socket")
    assert not await guard.allows_websocket("ws://localhost/socket")
