from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class SessionStatus(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"


ACTIVE_STATUSES = (SessionStatus.STARTING, SessionStatus.RUNNING, SessionStatus.STOPPING)


@dataclass(frozen=True, slots=True)
class BrowserSession:
    id: str
    user_id: int
    status: SessionStatus
    runtime_id: str | None
    created_at: datetime
    last_activity: datetime
    expires_at: datetime
    ended_at: datetime | None
    end_reason: str | None
