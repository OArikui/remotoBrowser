from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import csrf, login

PROTECTED = [
    ("GET", "/api/me"),
    ("GET", "/api/session"),
    ("GET", "/api/browser/status"),
    ("POST", "/api/browser/start"),
    ("POST", "/api/browser/stop"),
    ("POST", "/api/browser/navigate"),
    ("POST", "/api/browser/activity"),
    ("POST", "/auth/logout"),
]


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_unauthenticated_requests_are_rejected(client: TestClient, method: str, path: str) -> None:
    assert client.request(method, path, json={"action": "reload"}).status_code == 401


@pytest.mark.parametrize(("method", "path"), [p for p in PROTECTED if p[0] == "POST"])
def test_state_changing_requests_need_csrf_token(
    client: TestClient, method: str, path: str
) -> None:
    login(client)
    body = {"action": "reload"}
    assert client.request(method, path, json=body).status_code == 403
    assert client.request(method, path, json=body, headers=csrf("wrong")).status_code == 403


def test_foreign_origin_is_rejected_even_with_valid_token(client: TestClient) -> None:
    token = login(client)
    headers = {**csrf(token), "Origin": "https://evil.example"}
    assert client.post("/api/browser/start", headers=headers, json={}).status_code == 403


def test_csrf_token_is_bound_to_session(client: TestClient) -> None:
    token_a = login(client, "1001")
    login(client, "1002")  # 新しいセッション(別のCSRFトークン)
    r = client.post("/api/browser/start", headers=csrf(token_a), json={})
    assert r.status_code == 403


def test_tampered_session_cookie_is_rejected(client: TestClient) -> None:
    login(client)
    cookie = client.cookies["rb_session"]
    client.cookies.set("rb_session", cookie[:-3] + "xxx")
    assert client.get("/api/me").status_code == 401


def test_removed_from_allow_list_loses_access(env_factory) -> None:
    env = env_factory(allowed_discord_ids="1001")
    with TestClient(env.app) as client:
        login(client, "1001")
        assert client.get("/api/me").status_code == 200
        # 運用中に許可リストから外された場合、既存Cookieでも即座に拒否される
        env.app.state.container.users._allowed = frozenset({"2002"})
        assert client.get("/api/me").status_code == 401
