from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from package.auth.dependencies import CurrentUser

router = APIRouter(prefix="/api", tags=["users"])


@router.get("/me")
async def me(ctx: CurrentUser) -> dict[str, Any]:
    user = ctx.user
    avatar_url = (
        f"https://cdn.discordapp.com/avatars/{user.discord_id}/{user.avatar}.png?size=64"
        if user.avatar
        else None
    )
    return {
        "id": user.id,
        "discord_id": user.discord_id,
        "username": user.username,
        "avatar_url": avatar_url,
        "csrf_token": ctx.csrf_token,
    }
