from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from fastapi import APIRouter, Request, WebSocket

from package.auth.dependencies import CurrentUser, authenticate
from package.security.access_control import authorize_vnc
from package.state import container

log = logging.getLogger("rb.security")

router = APIRouter(tags=["sessions"])


@router.get("/api/session")
async def get_session(request: Request, ctx: CurrentUser) -> dict[str, Any]:
    c = container(request)
    return c.browser_service.describe(c.sessions.get_for_user(ctx.user.id))


@router.websocket("/ws/vnc/{session_id}")
async def vnc_proxy(websocket: WebSocket, session_id: str) -> None:
    """noVNC ⇔ 127.0.0.1のVNCポートの中継。認証済みの所有者にだけ接続を許可する。"""
    c = container(websocket)

    origin = websocket.headers.get("origin")
    if origin is not None and origin != c.settings.origin:
        log.warning("websocket rejected: unexpected origin")
        await websocket.close(code=4403)
        return
    ctx = authenticate(websocket)
    if ctx is None:
        await websocket.close(code=4401)
        return
    port = authorize_vnc(c.sessions, session_id, ctx.user.id)
    if port is None:
        log.warning("websocket rejected: session not owned or not running user=%s", ctx.user.id)
        await websocket.close(code=4403)
        return

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
    except OSError:
        await websocket.close(code=1011)
        return

    offered = websocket.scope.get("subprotocols", [])
    await websocket.accept(subprotocol="binary" if "binary" in offered else None)

    async def ws_to_tcp() -> None:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            data = message.get("bytes")
            if data is None and message.get("text") is not None:
                data = message["text"].encode()
            if data:
                writer.write(data)
                await writer.drain()

    async def tcp_to_ws() -> None:
        while data := await reader.read(65536):
            await websocket.send_bytes(data)

    tasks = {asyncio.create_task(ws_to_tcp()), asyncio.create_task(tcp_to_ws())}
    cancelled = False
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except asyncio.CancelledError:
        # Treat ASGI task cancellation during a WebSocket disconnect as tunnel shutdown.
        # The cleanup below must finish before this connection handler returns.
        cancelled = True
        log.debug("VNC proxy cancelled during disconnect session=%s", session_id)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        writer.close()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(writer.wait_closed(), timeout=2)
        if not cancelled:
            with contextlib.suppress(Exception):
                await websocket.close()
