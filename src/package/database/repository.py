from __future__ import annotations

import sqlite3
from datetime import datetime

from package.sessions.models import BrowserSession, SessionStatus
from package.utils import from_iso, to_iso

from .connection import Database
from .models import User, UserSettings


def _user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        discord_id=row["discord_id"],
        username=row["username"],
        avatar=row["avatar"],
        created_at=from_iso(row["created_at"]),
        last_login=from_iso(row["last_login"]),
    )


def _session(row: sqlite3.Row) -> BrowserSession:
    return BrowserSession(
        id=row["id"],
        user_id=row["user_id"],
        status=SessionStatus(row["status"]),
        runtime_id=row["runtime_id"],
        created_at=from_iso(row["created_at"]),
        last_activity=from_iso(row["last_activity"]),
        expires_at=from_iso(row["expires_at"]),
        ended_at=from_iso(row["ended_at"]) if row["ended_at"] else None,
        end_reason=row["end_reason"],
    )


_ACTIVE_SQL = "('starting','running','stopping')"


class Repository:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ---- users ----
    def upsert_user(
        self, discord_id: str, username: str, avatar: str | None, now: datetime
    ) -> User:
        stamp = to_iso(now)
        with self._db.connect() as conn:
            conn.execute(
                """
                INSERT INTO users (discord_id, username, avatar, created_at, last_login)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(discord_id) DO UPDATE SET
                    username = excluded.username,
                    avatar = excluded.avatar,
                    last_login = excluded.last_login
                """,
                (discord_id, username, avatar, stamp, stamp),
            )
            row = conn.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,)).fetchone()
            conn.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (row["id"],))
            return _user(row)

    def get_user(self, user_id: int) -> User | None:
        with self._db.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return _user(row) if row else None

    def get_settings(self, user_id: int) -> UserSettings | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
            ).fetchone()
            if row is None:
                return None
            return UserSettings(
                user_id=row["user_id"],
                default_url=row["default_url"],
                theme=row["theme"],
                language=row["language"],
            )

    # ---- browser sessions ----
    def create_session(
        self, session_id: str, user_id: int, now: datetime, expires_at: datetime
    ) -> None:
        """status=starting で作成。同一ユーザーに有効なセッションがあれば IntegrityError。"""
        with self._db.connect() as conn:
            conn.execute(
                """
                INSERT INTO browser_sessions
                    (id, user_id, status, created_at, last_activity, expires_at)
                VALUES (?, ?, 'starting', ?, ?, ?)
                """,
                (session_id, user_id, to_iso(now), to_iso(now), to_iso(expires_at)),
            )

    def mark_running(self, session_id: str, runtime_id: str) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE browser_sessions SET status = 'running', runtime_id = ? WHERE id = ?",
                (runtime_id, session_id),
            )

    def set_status(self, session_id: str, status: SessionStatus) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE browser_sessions SET status = ? WHERE id = ?", (status.value, session_id)
            )

    def touch_session(self, session_id: str, now: datetime) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE browser_sessions SET last_activity = ? WHERE id = ?",
                (to_iso(now), session_id),
            )

    def end_session(self, session_id: str, reason: str, now: datetime) -> None:
        with self._db.connect() as conn:
            conn.execute(
                """
                UPDATE browser_sessions
                SET status = 'stopped', ended_at = ?, end_reason = ?
                WHERE id = ?
                """,
                (to_iso(now), reason, session_id),
            )

    def end_all_active(self, reason: str, now: datetime) -> int:
        with self._db.connect() as conn:
            cur = conn.execute(
                f"""
                UPDATE browser_sessions
                SET status = 'stopped', ended_at = ?, end_reason = ?
                WHERE status IN {_ACTIVE_SQL}
                """,
                (to_iso(now), reason),
            )
            return cur.rowcount

    def get_session(self, session_id: str) -> BrowserSession | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM browser_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            return _session(row) if row else None

    def get_active_session_for_user(self, user_id: int) -> BrowserSession | None:
        with self._db.connect() as conn:
            row = conn.execute(
                f"SELECT * FROM browser_sessions WHERE user_id = ? AND status IN {_ACTIVE_SQL}",
                (user_id,),
            ).fetchone()
            return _session(row) if row else None
