from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from tests.conftest import Env, EnvFactory, csrf, login, run_async


def _start(client: TestClient, token: str, **body: str) -> dict[str, object]:
    r = client.post("/api/browser/start", headers=csrf(token), json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_start_status_stop(client: TestClient, env: Env) -> None:
    token = login(client)
    assert client.get("/api/session").json() == {"status": "none"}

    info = _start(client, token)
    assert info["status"] == "running"
    assert info["remaining_seconds"] == env.settings.session_max_seconds
    assert info["vnc_path"] == f"/ws/vnc/{info['session_id']}"
    assert client.get("/api/browser/status").json()["status"] == "running"
    assert len(env.runtime.active) == 1

    r = client.post("/api/browser/stop", headers=csrf(token))
    assert r.json() == {"stopped": True}
    assert client.get("/api/session").json() == {"status": "none"}
    assert env.runtime.active == {}
    assert client.post("/api/browser/stop", headers=csrf(token)).json() == {"stopped": False}


def test_start_is_idempotent(client: TestClient, env: Env) -> None:
    token = login(client)
    first = _start(client, token)
    second = _start(client, token)
    assert first["session_id"] == second["session_id"]
    assert len(env.runtime.active) == 1


def test_capacity_limit(client: TestClient) -> None:
    token_a = login(client, "1001")
    _start(client, token_a)
    token_b = login(client, "1002")
    r = client.post("/api/browser/start", headers=csrf(token_b), json={})
    assert r.status_code == 503


def test_capacity_allows_more_when_configured(env_factory: EnvFactory) -> None:
    env = env_factory(max_concurrent_sessions=2)
    with TestClient(env.app) as client:
        _start(client, login(client, "1001"))
        _start(client, login(client, "1002"))
        assert len(env.runtime.active) == 2


def test_start_rejects_private_url(client: TestClient, env: Env) -> None:
    token = login(client)
    r = client.post("/api/browser/start", headers=csrf(token), json={"url": "http://localhost/"})
    assert r.status_code == 400
    assert env.runtime.active == {}
    assert client.get("/api/session").json() == {"status": "none"}
    # 失敗後も通常どおり起動できる
    _start(client, token)


def test_start_failure_is_cleaned_up(client: TestClient, env: Env, monkeypatch) -> None:
    token = login(client)

    async def boom(session_id: str, start_url: str) -> None:
        raise RuntimeError("chromium missing")

    monkeypatch.setattr(env.runtime, "start", boom)
    r = client.post("/api/browser/start", headers=csrf(token), json={})
    assert r.status_code == 502
    assert client.get("/api/session").json() == {"status": "none"}


def test_session_expires(client: TestClient, env: Env) -> None:
    token = login(client)
    sid = str(_start(client, token)["session_id"])
    env.clock.advance(env.settings.session_max_seconds + 1)
    run_async(client, env.sessions.sweep)

    assert client.get("/api/session").json() == {"status": "none"}
    assert env.runtime.active == {}
    ended = env.repo.get_session(sid)
    assert ended.end_reason == "expired"
    assert ended.ended_at is not None


def test_idle_timeout_and_heartbeat(client: TestClient, env: Env) -> None:
    token = login(client)
    sid = str(_start(client, token)["session_id"])
    idle = env.settings.idle_timeout_seconds

    env.clock.advance(idle - 100)
    assert client.post("/api/browser/activity", headers=csrf(token)).json() == {"active": True}
    env.clock.advance(idle - 100)  # 開始から見ればアイドル超過だが、直前に操作通知がある
    run_async(client, env.sessions.sweep)
    assert client.get("/api/session").json()["status"] == "running"

    env.clock.advance(idle + 1)
    run_async(client, env.sessions.sweep)
    assert client.get("/api/session").json() == {"status": "none"}
    assert env.repo.get_session(sid).end_reason == "idle"


def test_crashed_browser_is_collected(client: TestClient, env: Env) -> None:
    token = login(client)
    sid = str(_start(client, token)["session_id"])
    runtime_id = next(iter(env.runtime.active))
    env.runtime.kill(runtime_id)

    run_async(client, env.sessions.sweep)
    assert client.get("/api/session").json() == {"status": "none"}
    assert env.repo.get_session(sid).end_reason == "crashed"
    assert env.runtime.active == {}


def test_stale_sessions_closed_on_startup(client: TestClient, env: Env) -> None:
    login(client)
    user = env.repo.upsert_user("9999", "ghost", None, env.clock())
    env.repo.create_session("stale", user.id, env.clock(), env.clock() + timedelta(minutes=30))
    env.repo.mark_running("stale", "gone")

    run_async(client, env.sessions.reconcile_on_startup)
    stale = env.repo.get_session("stale")
    assert stale.status.value == "stopped"
    assert stale.end_reason == "restart"
    assert env.repo.get_active_session_for_user(user.id) is None


def test_stale_record_is_replaced_on_start(client: TestClient, env: Env) -> None:
    token = login(client)
    me = client.get("/api/me").json()
    env.repo.create_session("stale", me["id"], env.clock(), env.clock() + timedelta(minutes=30))
    env.repo.mark_running("stale", "gone")  # 実体(プロセス)のない記録

    info = _start(client, token)
    assert info["session_id"] != "stale"
    assert env.repo.get_session("stale").end_reason == "replaced"


def test_navigation(client: TestClient, env: Env) -> None:
    token = login(client)
    nav = "/api/browser/navigate"
    r = client.post(nav, headers=csrf(token), json={"action": "reload"})
    assert r.status_code == 409  # ブラウザ未起動

    _start(client, token)
    runtime_id = next(iter(env.runtime.active))
    calls = env.runtime.active[runtime_id].calls

    assert client.post(nav, headers=csrf(token), json={"action": "back"}).status_code == 200
    r = client.post(nav, headers=csrf(token), json={"action": "goto", "url": "example.com/x"})
    assert r.status_code == 200
    assert calls[-2:] == [("back", None), ("goto", "https://example.com/x")]

    for bad in ("http://internal.example/", "http://localhost:8000/", "file:///etc/passwd"):
        r = client.post(nav, headers=csrf(token), json={"action": "goto", "url": bad})
        assert r.status_code == 400, bad
    r = client.post(nav, headers=csrf(token), json={"action": "goto"})
    assert r.status_code == 400
    r = client.post(nav, headers=csrf(token), json={"action": "explode"})
    assert r.status_code == 422
    assert calls[-1] == ("goto", "https://example.com/x")  # 拒否したURLは実行されていない


def test_start_rate_limited(env_factory: EnvFactory) -> None:
    env = env_factory(rate_limit_start_per_minute=2)
    with TestClient(env.app) as client:
        token = login(client)
        codes = [
            client.post("/api/browser/start", headers=csrf(token), json={}).status_code
            for _ in range(3)
        ]
        assert codes == [200, 200, 429]
