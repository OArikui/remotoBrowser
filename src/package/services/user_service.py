from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from package.auth.discord import DiscordUser
from package.database.models import User
from package.database.repository import Repository
from package.utils import utcnow

log = logging.getLogger("rb.auth")


class NotAllowedError(Exception):
    """許可リストにないDiscordアカウント。"""


class UserService:
    def __init__(
        self,
        repo: Repository,
        allowed_ids: frozenset[str],
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._repo = repo
        self._allowed = allowed_ids
        self._clock = clock

    def is_allowed(self, discord_id: str) -> bool:
        """許可リストが空なら全員許可。"""
        return not self._allowed or discord_id in self._allowed

    def login(self, discord_user: DiscordUser) -> User:
        if not self.is_allowed(discord_user.id):
            log.warning("login rejected: discord id not in allow-list")
            raise NotAllowedError(discord_user.id)
        user = self._repo.upsert_user(
            discord_user.id, discord_user.username, discord_user.avatar, self._clock()
        )
        log.info("login ok user=%s", user.id)
        return user

    def get(self, user_id: int) -> User | None:
        return self._repo.get_user(user_id)
