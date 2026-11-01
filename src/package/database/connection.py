from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .models import SCHEMA


class Database:
    """SQLite接続の薄いラッパー。

    呼び出しごとに接続を開いて閉じる(スレッド安全・実装が単純)。
    PostgreSQLへ移行する場合は Repository の実装だけを差し替える。
    注意: ``:memory:`` は接続ごとに別DBになるため使えない。
    """

    def __init__(self, path: str) -> None:
        self.path = path

    def init(self) -> None:
        parent = Path(self.path).parent
        parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:  # 正常終了でcommit、例外でrollback
                yield conn
        finally:
            conn.close()
