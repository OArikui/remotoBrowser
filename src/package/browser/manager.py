from __future__ import annotations

from .policies import UrlChecker, UrlNotAllowed, check_url, normalize_url
from .runtime import BrowserRuntime, RuntimeHandle


class BrowserManager:
    """ポリシー検査を挟んでランタイムを操作する窓口。"""

    def __init__(
        self,
        runtime: BrowserRuntime,
        default_url: str,
        url_checker: UrlChecker = check_url,
    ) -> None:
        self._runtime = runtime
        self._default_url = default_url
        self._check = url_checker

    async def launch(self, session_id: str, url: str | None = None) -> RuntimeHandle:
        target = normalize_url(url or self._default_url)
        await self._check(target)
        return await self._runtime.start(session_id, target)

    async def terminate(self, runtime_id: str) -> None:
        await self._runtime.stop(runtime_id)

    def is_alive(self, runtime_id: str) -> bool:
        return self._runtime.is_alive(runtime_id)

    async def navigate(self, runtime_id: str, action: str, url: str | None = None) -> None:
        if action == "goto":
            if not url:
                raise UrlNotAllowed("URL is required")
            target = normalize_url(url)
            await self._check(target)
            await self._runtime.navigate(runtime_id, "goto", target)
        else:
            await self._runtime.navigate(runtime_id, action, None)

    async def shutdown(self) -> None:
        await self._runtime.shutdown()
