from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import EnvFactory


def test_security_headers_present(client: TestClient) -> None:
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    csp = r.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "ws://" in csp


def test_api_responses_are_not_cached(client: TestClient) -> None:
    assert client.get("/api/me").headers["cache-control"] == "no-store"


def test_docs_disabled_by_default(client: TestClient) -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_session_cookie_flags(client: TestClient) -> None:
    r = client.get("/auth/discord", follow_redirects=False)
    state_cookie = r.headers["set-cookie"].lower()
    assert "httponly" in state_cookie
    assert "samesite=lax" in state_cookie
    assert "secure" not in state_cookie.replace("samesite", "")  # http開発時のみ


def test_cookies_are_secure_over_https(env_factory: EnvFactory) -> None:
    env = env_factory(base_url="https://rb.example.com")
    with TestClient(env.app) as client:
        r = client.get("/auth/discord", follow_redirects=False)
        assert "secure" in r.headers["set-cookie"].lower()
        assert "wss://rb.example.com" in client.get("/health").headers["content-security-policy"]
