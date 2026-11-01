"""共通ユーティリティ。"""

from __future__ import annotations

import logging
import secrets
import sys
from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds")


def from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def new_id(nbytes: int = 24) -> str:
    return secrets.token_urlsafe(nbytes)


def configure_logging(level: str) -> None:
    """標準出力へログを出す。トークン・Cookie・閲覧内容は絶対に記録しない。"""
    logging.basicConfig(
        level=level.upper(),
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
