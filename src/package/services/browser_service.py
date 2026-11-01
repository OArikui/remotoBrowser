from __future__ import annotations

from typing import Any

from package.config import Settings
from package.database.models import User
from package.database.repository import Repository
from package.sessions.manager import SessionManager
from package.sessions.models import BrowserSession
from package.utils import to_iso


class BrowserService:
    """ユーザー向けのブラウザ操作(設定の反映・レスポンス整形)。"""

    def __init__(self, sessions: SessionManager, repo: Repository, settings: Settings) -> None:
        self._sessions = sessions
        self._repo = repo
        self._settings = settings

    async def start(self, user: User, url: str | None) -> dict[str, Any]:
        target = url
        if target is None:
            user_settings = self._repo.get_settings(user.id)
            if user_settings is not None and user_settings.default_url:
                target = user_settings.default_url
        session = await self._sessions.start(user.id, target)
        return self.describe(session)

    async def stop(self, user: User) -> bool:
        return await self._sessions.stop(user.id, "user")

    async def navigate(self, user: User, action: str, url: str | None) -> None:
        await self._sessions.navigate(user.id, action, url)

    def heartbeat(self, user: User) -> bool:
        session = self._sessions.get_for_user(user.id)
        if session is None:
            return False
        self._sessions.touch(session.id)
        return True

    def status(self, user: User) -> dict[str, Any]:
        session = self._sessions.get_for_user(user.id)
        if session is None:
            return {"status": "none"}
        return {"status": session.status.value, "remaining_seconds": self._remaining(session)}

    def describe(self, session: BrowserSession | None) -> dict[str, Any]:
        if session is None:
            return {"status": "none"}
        return {
            "status": session.status.value,
            "session_id": session.id,
            "created_at": to_iso(session.created_at),
            "expires_at": to_iso(session.expires_at),
            "remaining_seconds": self._remaining(session),
            "idle_timeout_seconds": self._settings.idle_timeout_seconds,
            "vnc_path": f"/ws/vnc/{session.id}",
        }

    def _remaining(self, session: BrowserSession) -> int:
        return max(0, int((session.expires_at - self._sessions.now()).total_seconds()))
