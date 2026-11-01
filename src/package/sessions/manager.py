from __future__ import annotations

import asyncio
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from package.browser.manager import BrowserManager
from package.browser.policies import UrlNotAllowed
from package.browser.runtime import RuntimeHandle
from package.config import Settings
from package.database.repository import Repository
from package.utils import new_id, utcnow

from .models import BrowserSession, SessionStatus

log = logging.getLogger("rb.session")

_DB_TOUCH_INTERVAL = timedelta(seconds=10)


class SessionError(Exception):
    """セッション操作の失敗(基底)。"""


class CapacityError(SessionError):
    """同時セッション数の上限に達している。"""


class BrowserStartError(SessionError):
    """ブラウザの起動に失敗した。"""


class NoActiveSession(SessionError):
    """有効なセッションがない。"""


@dataclass
class _Active:
    handle: RuntimeHandle
    last_activity: datetime
    last_db_write: datetime


class SessionManager:
    """利用者とブラウザ実行環境の対応・有効期限・回収を管理する。"""

    def __init__(
        self,
        repo: Repository,
        browser: BrowserManager,
        settings: Settings,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._repo = repo
        self._browser = browser
        self._settings = settings
        self._clock = clock
        self._active: dict[str, _Active] = {}
        self._lock = asyncio.Lock()

    def now(self) -> datetime:
        return self._clock()

    # ---- 起動・終了 ----
    async def start(self, user_id: int, url: str | None = None) -> BrowserSession:
        async with self._lock:
            existing = self._repo.get_active_session_for_user(user_id)
            if existing is not None:
                if existing.status is SessionStatus.RUNNING and existing.id in self._active:
                    return existing  # 冪等: 既に起動済み
                await self._finish(existing, "replaced")  # 実体のない古い記録を片付ける

            if len(self._active) >= self._settings.max_concurrent_sessions:
                raise CapacityError("no free browser slot")

            now = self._clock()
            session_id = new_id()
            expires_at = now + timedelta(seconds=self._settings.session_max_seconds)
            try:
                self._repo.create_session(session_id, user_id, now, expires_at)
            except sqlite3.IntegrityError as exc:
                raise SessionError("an active session already exists") from exc

            try:
                handle = await self._browser.launch(session_id, url)
            except UrlNotAllowed:
                self._repo.end_session(session_id, "rejected_url", self._clock())
                raise
            except asyncio.CancelledError:
                self._repo.end_session(session_id, "cancelled", self._clock())
                raise
            except Exception as exc:
                log.exception("browser start failed session=%s", session_id)
                self._repo.end_session(session_id, "start_failed", self._clock())
                raise BrowserStartError("failed to start the browser") from exc

            self._active[session_id] = _Active(handle, now, now)
            self._repo.mark_running(session_id, handle.runtime_id)
            session = self._repo.get_session(session_id)
            if session is None:  # pragma: no cover - 直前にINSERT済み
                raise SessionError("session vanished")
            log.info("session started id=%s user=%s", session_id, user_id)
            return session

    async def stop(self, user_id: int, reason: str = "user") -> bool:
        async with self._lock:
            session = self._repo.get_active_session_for_user(user_id)
            if session is None:
                return False
            await self._finish(session, reason)
            return True

    async def _finish(self, session: BrowserSession, reason: str) -> None:
        self._repo.set_status(session.id, SessionStatus.STOPPING)
        active = self._active.pop(session.id, None)
        runtime_id = active.handle.runtime_id if active else session.runtime_id
        if runtime_id:
            try:
                await self._browser.terminate(runtime_id)
            except Exception:
                log.exception("failed to terminate runtime session=%s", session.id)
        self._repo.end_session(session.id, reason, self._clock())
        log.info("session ended id=%s reason=%s", session.id, reason)

    # ---- 参照 ----
    def get_for_user(self, user_id: int) -> BrowserSession | None:
        return self._repo.get_active_session_for_user(user_id)

    def get_running(self, session_id: str) -> BrowserSession | None:
        session = self._repo.get_session(session_id)
        if session is None or session.status is not SessionStatus.RUNNING:
            return None
        return session if session_id in self._active else None

    def vnc_port(self, session_id: str) -> int | None:
        active = self._active.get(session_id)
        return active.handle.vnc_port if active else None

    # ---- 操作 ----
    def touch(self, session_id: str) -> None:
        active = self._active.get(session_id)
        if active is None:
            return
        now = self._clock()
        active.last_activity = now
        if now - active.last_db_write >= _DB_TOUCH_INTERVAL:
            self._repo.touch_session(session_id, now)
            active.last_db_write = now

    async def navigate(self, user_id: int, action: str, url: str | None = None) -> None:
        session = self.get_for_user(user_id)
        if session is None or session.id not in self._active:
            raise NoActiveSession("no running browser")
        await self._browser.navigate(self._active[session.id].handle.runtime_id, action, url)
        self.touch(session.id)

    # ---- 保守 ----
    async def sweep(self) -> None:
        """期限切れ・アイドル・異常終了したセッションを回収する。"""
        for session_id, active in list(self._active.items()):
            now = self._clock()
            session = self._repo.get_session(session_id)
            reason: str | None = None
            if session is None:
                reason = "orphaned"
            elif not self._browser.is_alive(active.handle.runtime_id):
                reason = "crashed"
            elif now >= session.expires_at:
                reason = "expired"
            elif now - active.last_activity > timedelta(
                seconds=self._settings.idle_timeout_seconds
            ):
                reason = "idle"
            if reason is None or session is None:
                continue
            async with self._lock:
                current = self._repo.get_session(session_id)
                if current is not None and session_id in self._active:
                    await self._finish(current, reason)

    async def reconcile_on_startup(self) -> None:
        """再起動後は以前のブラウザプロセスが存在すると仮定しない。"""
        count = self._repo.end_all_active("restart", self._clock())
        if count:
            log.warning("closed %s stale session(s) left from a previous run", count)

    async def shutdown(self) -> None:
        async with self._lock:
            for session_id in list(self._active):
                session = self._repo.get_session(session_id)
                if session is not None:
                    await self._finish(session, "shutdown")
