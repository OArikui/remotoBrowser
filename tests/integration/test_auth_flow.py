from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from tests.conftest import Env, EnvFactory, csrf, login


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_unauthenticated_me(client: TestClient) -> None:
    assert client.get("/api/me").status_code == 401


def test_login_success_and_user_saved(client: TestClient, env: Env) -> None:
    login(client, "1001")
    body = client.get("/api/me").json()
    assert body["discord_id"] == "1001"
    assert body["username"] == "user1001"
    # アクセストークンは認証後に失効させる
    assert env.discord.revoked == ["token-1001"]


def test_login_redirect_targets_discord(client: TestClient) -> None:
    r = client.get("/auth/discord", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("https://discord.test/authorize")
    assert "rb_oauth_state" in r.headers["set-cookie"]
    assert "HttpOnly" in r.headers["set-cookie"]


def test_callback_rejects_wrong_state(client: TestClient) -> None:
    client.get("/auth/discord", follow_redirects=False)
    r = client.get("/auth/callback", params={"code": "1001", "state": "forged"})
    assert r.status_code == 400
    assert client.get("/api/me").status_code == 401


def test_callback_rejects_missing_state_cookie(client: TestClient) -> None:
    r = client.get("/auth/callback", params={"code": "1001", "state": "x"})
    assert r.status_code == 400


def test_callback_user_denied(client: TestClient) -> None:
    client.get("/auth/discord", follow_redirects=False)
    r = client.get("/auth/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/login.html?error=denied"


def test_callback_discord_failure(client: TestClient) -> None:
    r = client.get("/auth/discord", follow_redirects=False)
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    r = client.get("/auth/callback", params={"code": "bad", "state": state}, follow_redirects=False)
    assert r.headers["location"] == "/login.html?error=discord"
    assert client.get("/api/me").status_code == 401


def test_allow_list(env_factory: EnvFactory) -> None:
    env = env_factory(allowed_discord_ids="2002")
    with TestClient(env.app) as client:
        r = client.get("/auth/discord", follow_redirects=False)
        state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
        r = client.get(
            "/auth/callback", params={"code": "1001", "state": state}, follow_redirects=False
        )
        assert r.headers["location"] == "/login.html?error=not_allowed"
        assert client.get("/api/me").status_code == 401
        login(client, "2002")
        assert client.get("/api/me").status_code == 200


def test_logout_clears_session_and_stops_browser(client: TestClient, env: Env) -> None:
    token = login(client)
    assert client.post("/api/browser/start", headers=csrf(token), json={}).status_code == 200
    assert len(env.runtime.active) == 1

    assert client.post("/auth/logout", headers=csrf(token)).status_code == 200
    assert client.get("/api/me").status_code == 401
    assert env.runtime.active == {}  # ログアウトでブラウザも破棄


def test_oauth_not_configured(env_factory: EnvFactory) -> None:
    env = env_factory()
    env.discord.configured = False  # type: ignore[misc]
    with TestClient(env.app) as client:
        assert client.get("/auth/discord", follow_redirects=False).status_code == 503


def test_login_rate_limited(env_factory: EnvFactory) -> None:
    env = env_factory(rate_limit_login_per_minute=3)
    with TestClient(env.app) as client:
        codes = [client.get("/auth/discord", follow_redirects=False).status_code for _ in range(5)]
        assert codes == [302, 302, 302, 429, 429]
