from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.conftest import Env, csrf, login, run_async


def _start(client: TestClient, token: str) -> str:
    r = client.post("/api/browser/start", headers=csrf(token), json={})
    assert r.status_code == 200, r.text
    return str(r.json()["session_id"])


def test_owner_can_proxy_vnc(client: TestClient) -> None:
    token = login(client)
    sid = _start(client, token)
    with client.websocket_connect(f"/ws/vnc/{sid}") as ws:
        assert ws.receive_bytes() == b"RFB 003.008\n"  # VNCサーバーのバナー
        ws.send_bytes(b"RFB 003.008\n")
        assert ws.receive_bytes() == b"RFB 003.008\n"  # エコー(双方向に中継できている)
        ws.send_bytes(b"\x04\x01\x00\x00\x00\x00\x00\x61")
        assert ws.receive_bytes() == b"\x04\x01\x00\x00\x00\x00\x00\x61"


def test_binary_subprotocol_is_negotiated(client: TestClient) -> None:
    token = login(client)
    sid = _start(client, token)
    with client.websocket_connect(f"/ws/vnc/{sid}", subprotocols=["binary"]) as ws:
        assert ws.accepted_subprotocol == "binary"


def test_unauthenticated_websocket_rejected(client: TestClient) -> None:
    token = login(client)
    sid = _start(client, token)
    client.cookies.clear()
    with pytest.raises(WebSocketDisconnect) as exc, client.websocket_connect(f"/ws/vnc/{sid}"):
        pass
    assert exc.value.code == 4401


def test_other_users_session_is_not_reachable(client: TestClient) -> None:
    token_a = login(client, "1001")
    sid = _start(client, token_a)

    login(client, "1002")  # 別ユーザーとしてログインし直す
    with pytest.raises(WebSocketDisconnect) as exc, client.websocket_connect(f"/ws/vnc/{sid}"):
        pass
    assert exc.value.code == 4403
    assert client.get("/api/session").json() == {"status": "none"}  # 他人のセッションは見えない


def test_unknown_session_rejected(client: TestClient) -> None:
    login(client)
    with pytest.raises(WebSocketDisconnect) as exc, client.websocket_connect("/ws/vnc/nope"):
        pass
    assert exc.value.code == 4403


def test_foreign_origin_rejected(client: TestClient) -> None:
    token = login(client)
    sid = _start(client, token)
    headers = {"origin": "https://evil.example"}
    with (
        pytest.raises(WebSocketDisconnect) as exc,
        client.websocket_connect(f"/ws/vnc/{sid}", headers=headers),
    ):
        pass
    assert exc.value.code == 4403


def test_same_origin_accepted(client: TestClient, env: Env) -> None:
    token = login(client)
    sid = _start(client, token)
    headers = {"origin": env.settings.origin}
    with client.websocket_connect(f"/ws/vnc/{sid}", headers=headers) as ws:
        assert ws.receive_bytes() == b"RFB 003.008\n"


def test_websocket_rejected_after_session_ends(client: TestClient, env: Env) -> None:
    token = login(client)
    sid = _start(client, token)
    run_async(client, env.sessions.stop, 1)
    with pytest.raises(WebSocketDisconnect) as exc, client.websocket_connect(f"/ws/vnc/{sid}"):
        pass
    assert exc.value.code == 4403
