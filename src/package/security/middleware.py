from __future__ import annotations

import time
from collections import deque
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, ws_origin: str) -> None:
        super().__init__(app)
        self._csp = "; ".join(
            [
                "default-src 'self'",
                "script-src 'self'",
                "style-src 'self' 'unsafe-inline'",
                "img-src 'self' data: https://cdn.discordapp.com",
                f"connect-src 'self' {ws_origin}",
                "frame-ancestors 'none'",
                "base-uri 'none'",
                "form-action 'self'",
            ]
        )

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("Content-Security-Policy", self._csp)
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "same-origin")
        headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.path.startswith(("/api/", "/auth/")):
            headers["Cache-Control"] = "no-store"
        return response


class RateLimiter:
    """単純なスライディングウィンドウ式のレート制限(インメモリ・単一インスタンス用)。"""

    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._events: dict[str, deque[float]] = {}

    def hit(self, key: str) -> bool:
        """記録して許可なら True、上限超過なら False。"""
        now = self._clock()
        if len(self._events) > 10_000:
            self._events = {
                k: v for k, v in self._events.items() if v and v[-1] > now - self._window
            }
        events = self._events.setdefault(key, deque())
        while events and events[0] <= now - self._window:
            events.popleft()
        if len(events) >= self._limit:
            return False
        events.append(now)
        return True
