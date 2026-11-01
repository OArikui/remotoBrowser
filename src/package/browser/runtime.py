"""ブラウザ実行環境の抽象とテスト用Fake実装。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Protocol

from package.utils import new_id


@dataclass(frozen=True, slots=True)
class RuntimeHandle:
    runtime_id: str
    # 127.0.0.1限定のVNCポート。外部へは公開せず、APIのWebSocketプロキシ経由でのみ到達する。
    vnc_port: int


class BrowserRuntime(Protocol):
    async def start(self, session_id: str, start_url: str) -> RuntimeHandle: ...

    async def stop(self, runtime_id: str) -> None:
        """冪等。未知のIDは何もしない。"""
        ...

    def is_alive(self, runtime_id: str) -> bool: ...

    async def navigate(self, runtime_id: str, action: str, url: str | None) -> None: ...

    async def shutdown(self) -> None: ...


@dataclass
class _FakeInstance:
    server: asyncio.Server
    port: int
    calls: list[tuple[str, str | None]] = field(default_factory=list)
    alive: bool = True


class FakeRuntime:
    """UI確認・テスト用。VNCの代わりにバナーを返してエコーするTCPサーバーを立てる。"""

    def __init__(self) -> None:
        self.active: dict[str, _FakeInstance] = {}

    async def start(self, session_id: str, start_url: str) -> RuntimeHandle:
        server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        port = int(server.sockets[0].getsockname()[1])
        runtime_id = new_id(8)
        self.active[runtime_id] = _FakeInstance(server, port, [("start", start_url)])
        return RuntimeHandle(runtime_id, port)

    @staticmethod
    async def _serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            writer.write(b"RFB 003.008\n")
            await writer.drain()
            while data := await reader.read(4096):
                writer.write(data)
                await writer.drain()
        except ConnectionError:
            pass
        finally:
            writer.close()

    async def stop(self, runtime_id: str) -> None:
        inst = self.active.pop(runtime_id, None)
        if inst is not None:
            inst.server.close()
            inst.server.close_clients()

    def is_alive(self, runtime_id: str) -> bool:
        inst = self.active.get(runtime_id)
        return inst is not None and inst.alive

    async def navigate(self, runtime_id: str, action: str, url: str | None) -> None:
        self.active[runtime_id].calls.append((action, url))

    async def shutdown(self) -> None:
        for runtime_id in list(self.active):
            await self.stop(runtime_id)

    # ---- テスト用 ----
    def kill(self, runtime_id: str) -> None:
        """異常終了を再現する。"""
        self.active[runtime_id].alive = False
