"""テーブル定義(計画書 1-5)。パスワードやDiscordのトークンは保存しない。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_id  TEXT NOT NULL UNIQUE,
    username    TEXT NOT NULL,
    avatar      TEXT,
    created_at  TEXT NOT NULL,
    last_login  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS browser_sessions (
    id             TEXT PRIMARY KEY,
    user_id        INTEGER NOT NULL REFERENCES users(id),
    status         TEXT NOT NULL CHECK (status IN ('starting','running','stopping','stopped')),
    runtime_id     TEXT,
    created_at     TEXT NOT NULL,
    last_activity  TEXT NOT NULL,
    expires_at     TEXT NOT NULL,
    ended_at       TEXT,
    end_reason     TEXT
);

-- 1ユーザーにつき同時に有効なセッションは1つだけ(競合時もDB側で保証)
CREATE UNIQUE INDEX IF NOT EXISTS one_active_session_per_user
    ON browser_sessions(user_id)
    WHERE status IN ('starting','running','stopping');

CREATE TABLE IF NOT EXISTS user_settings (
    user_id      INTEGER PRIMARY KEY REFERENCES users(id),
    default_url  TEXT,
    theme        TEXT NOT NULL DEFAULT 'light',
    language     TEXT NOT NULL DEFAULT 'ja'
);
"""


@dataclass(frozen=True, slots=True)
class User:
    id: int
    discord_id: str
    username: str
    avatar: str | None
    created_at: datetime
    last_login: datetime


@dataclass(frozen=True, slots=True)
class UserSettings:
    user_id: int
    default_url: str | None
    theme: str
    language: str
