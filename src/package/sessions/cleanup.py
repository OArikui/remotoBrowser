from __future__ import annotations

import asyncio
import logging

from .manager import SessionManager

log = logging.getLogger("rb.session")


async def run_cleanup_loop(manager: SessionManager, interval: float) -> None:
    """一定間隔で期限切れ・異常終了セッションを回収する(キャンセルで停止)。"""
    while True:
        await asyncio.sleep(interval)
        try:
            await manager.sweep()
        except Exception:
            log.exception("session sweep failed")
