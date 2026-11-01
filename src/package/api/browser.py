from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from package.auth.dependencies import CurrentUser
from package.browser.policies import UrlNotAllowed
from package.security.csrf import CsrfUser
from package.sessions.manager import (
    BrowserStartError,
    CapacityError,
    NoActiveSession,
    SessionError,
)
from package.state import container

router = APIRouter(prefix="/api/browser", tags=["browser"])


class StartRequest(BaseModel):
    url: str | None = Field(default=None, max_length=2048)


class NavigateRequest(BaseModel):
    action: Literal["back", "forward", "reload", "goto"]
    url: str | None = Field(default=None, max_length=2048)


@router.post("/start")
async def start(
    request: Request, ctx: CsrfUser, body: StartRequest | None = None
) -> dict[str, Any]:
    c = container(request)
    if not c.start_limiter.hit(f"user:{ctx.user.id}"):
        raise HTTPException(status_code=429, detail="too many requests")
    try:
        return await c.browser_service.start(ctx.user, body.url if body else None)
    except UrlNotAllowed as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CapacityError as exc:
        raise HTTPException(
            status_code=503, detail="現在利用できる枠がありません。しばらくしてからお試しください。"
        ) from exc
    except BrowserStartError as exc:
        raise HTTPException(status_code=502, detail="ブラウザの起動に失敗しました。") from exc
    except SessionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/stop")
async def stop(request: Request, ctx: CsrfUser) -> dict[str, bool]:
    stopped = await container(request).browser_service.stop(ctx.user)
    return {"stopped": stopped}


@router.get("/status")
async def status(request: Request, ctx: CurrentUser) -> dict[str, Any]:
    return container(request).browser_service.status(ctx.user)


@router.post("/navigate")
async def navigate(request: Request, ctx: CsrfUser, body: NavigateRequest) -> dict[str, bool]:
    try:
        await container(request).browser_service.navigate(ctx.user, body.action, body.url)
    except UrlNotAllowed as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NoActiveSession as exc:
        raise HTTPException(status_code=409, detail="ブラウザが起動していません。") from exc
    return {"ok": True}


@router.post("/activity")
async def activity(request: Request, ctx: CsrfUser) -> dict[str, bool]:
    """フロントエンドからの操作通知。アイドルタイムアウトの起点になる。"""
    return {"active": container(request).browser_service.heartbeat(ctx.user)}
