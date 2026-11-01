"""実ブラウザの起動・終了管理(Xvfb + x11vnc + Playwright/Chromium)。

セッションごとに:
  1. 専用の仮想ディスプレイ(Xvfb)
  2. 127.0.0.1 限定のVNCサーバー(x11vnc)
  3. 使い捨てプロファイルのChromium(Playwrightが起動・制御)
を立ち上げ、終了時にすべて回収してプロファイルを削除する。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
import socket
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from package.utils import new_id

from .policies import NETWORK_SCHEMES, UrlChecker, UrlNotAllowed, check_url
from .runtime import RuntimeHandle

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page, Playwright, Request, Route

log = logging.getLogger("rb.browser")

_LOCAL_SCHEMES = frozenset({"data", "blob", "about"})
_X11_SOCKET_DIR = Path("/tmp/.X11-unix")


class RequestGuard:
    """ブラウザが発行するすべてのHTTP(S)リクエストの宛先を検査する(リダイレクト先も対象)。"""

    def __init__(self, checker: UrlChecker = check_url, ttl: float = 30.0) -> None:
        self._checker = checker
        self._ttl = ttl
        self._cache: dict[str, tuple[float, bool]] = {}

    async def allows(self, url: str) -> bool:
        parts = urlsplit(url)
        if parts.scheme in _LOCAL_SCHEMES:
            return True
        if parts.scheme not in NETWORK_SCHEMES:
            return False
        key = f"{parts.scheme}://{parts.hostname}:{parts.port}"
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]
        try:
            await self._checker(url)
            ok = True
        except UrlNotAllowed:
            ok = False
        if len(self._cache) > 1024:
            self._cache.clear()
        self._cache[key] = (now + self._ttl, ok)
        return ok


@dataclass
class _Instance:
    display: int
    vnc_port: int
    profile_dir: Path
    xvfb: asyncio.subprocess.Process | None = None
    x11vnc: asyncio.subprocess.Process | None = None
    context: BrowserContext | None = None
    closed: bool = False
    _extra: dict[str, Any] = field(default_factory=dict)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _terminate(proc: asyncio.subprocess.Process | None) -> None:
    if proc is None or proc.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.wait()


async def _wait_for(
    predicate: Callable[[], bool], proc: asyncio.subprocess.Process, what: str, limit: float
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + limit
    while loop.time() < deadline:
        if proc.returncode is not None:
            raise RuntimeError(f"{what} exited early (code {proc.returncode})")
        if predicate():
            return
        await asyncio.sleep(0.1)
    raise TimeoutError(f"{what} did not become ready within {limit}s")


async def _wait_for_port(port: int, proc: asyncio.subprocess.Process, limit: float) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + limit
    while loop.time() < deadline:
        if proc.returncode is not None:
            raise RuntimeError(f"x11vnc exited early (code {proc.returncode})")
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
        except OSError:
            await asyncio.sleep(0.2)
            continue
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()
        return
    raise TimeoutError(f"x11vnc did not listen on {port} within {limit}s")


class ProcessRuntime:
    def __init__(
        self,
        *,
        width: int,
        height: int,
        display_base: int = 100,
        profile_root: str | None = None,
        startup_timeout: float = 15.0,
        url_checker: UrlChecker = check_url,
    ) -> None:
        self._width = width
        self._height = height
        self._display_base = display_base
        self._profile_root = profile_root
        self._timeout = startup_timeout
        self._guard = RequestGuard(url_checker)
        self._instances: dict[str, _Instance] = {}
        self._used_displays: set[int] = set()
        self._lock = asyncio.Lock()
        self._pw: Playwright | None = None

    # ---- internals ----
    def _allocate_display(self) -> int:
        n = self._display_base
        while (
            n in self._used_displays
            or (_X11_SOCKET_DIR / f"X{n}").exists()
            or Path(f"/tmp/.X{n}-lock").exists()
        ):
            n += 1
        self._used_displays.add(n)
        return n

    async def _playwright(self) -> Playwright:
        if self._pw is None:
            from playwright.async_api import async_playwright

            self._pw = await async_playwright().start()
        return self._pw

    async def _start_display(self, inst: _Instance) -> None:
        inst.xvfb = await asyncio.create_subprocess_exec(
            "Xvfb",
            f":{inst.display}",
            "-screen",
            "0",
            f"{self._width}x{self._height}x24",
            "-nolisten",
            "tcp",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        sock = _X11_SOCKET_DIR / f"X{inst.display}"
        await _wait_for(sock.exists, inst.xvfb, "Xvfb", self._timeout)

        inst.x11vnc = await asyncio.create_subprocess_exec(
            "x11vnc",
            "-display",
            f":{inst.display}",
            "-rfbport",
            str(inst.vnc_port),
            "-localhost",  # 127.0.0.1 のみ。認証はAPIのプロキシが担う
            "-nopw",
            "-forever",
            "-shared",
            "-quiet",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await _wait_for_port(inst.vnc_port, inst.x11vnc, self._timeout)

    async def _start_chromium(self, inst: _Instance, start_url: str) -> None:
        pw = await self._playwright()
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(inst.profile_dir),
            headless=False,
            env={**os.environ, "DISPLAY": f":{inst.display}"},
            no_viewport=True,
            service_workers="block",  # route()で全リクエストを検査できるようにする
            accept_downloads=False,
            args=[
                f"--window-size={self._width},{self._height}",
                "--window-position=0,0",
                "--kiosk",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        inst.context = context
        context.on("close", lambda *_: setattr(inst, "closed", True))
        await context.route("**/*", self._route_handler)

        page = context.pages[0] if context.pages else await context.new_page()
        with contextlib.suppress(Exception):  # 読み込み失敗でもブラウザ自体は使える
            await page.goto(start_url, wait_until="commit", timeout=15_000)

    async def _route_handler(self, route: Route, request: Request) -> None:
        try:
            if await self._guard.allows(request.url):
                await route.continue_()
            else:
                log.warning("blocked request to non-public destination")
                await route.abort("blockedbyclient")
        except Exception:
            log.debug("route handler failed", exc_info=True)

    async def _teardown(self, runtime_id: str) -> None:
        inst = self._instances.pop(runtime_id, None)
        if inst is None:
            return
        inst.closed = True
        if inst.context is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(inst.context.close(), timeout=10)
        await _terminate(inst.x11vnc)
        await _terminate(inst.xvfb)
        shutil.rmtree(inst.profile_dir, ignore_errors=True)  # Cookie・履歴を残さない
        self._used_displays.discard(inst.display)

    # ---- BrowserRuntime ----
    async def start(self, session_id: str, start_url: str) -> RuntimeHandle:
        async with self._lock:
            display = self._allocate_display()
            vnc_port = _free_port()
        runtime_id = new_id(12)
        profile_dir = Path(tempfile.mkdtemp(prefix="rb-profile-", dir=self._profile_root))
        self._instances[runtime_id] = _Instance(display, vnc_port, profile_dir)
        inst = self._instances[runtime_id]
        try:
            await self._start_display(inst)
            await self._start_chromium(inst, start_url)
        except BaseException:
            await self._teardown(runtime_id)
            raise
        log.info("browser runtime started session=%s display=:%s", session_id, display)
        return RuntimeHandle(runtime_id, vnc_port)

    async def stop(self, runtime_id: str) -> None:
        await self._teardown(runtime_id)

    def is_alive(self, runtime_id: str) -> bool:
        inst = self._instances.get(runtime_id)
        if inst is None or inst.closed:
            return False
        procs = (inst.xvfb, inst.x11vnc)
        return all(p is not None and p.returncode is None for p in procs)

    def _page(self, runtime_id: str) -> Page:
        inst = self._instances.get(runtime_id)
        if inst is None or inst.context is None or not inst.context.pages:
            raise RuntimeError("browser is not running")
        return inst.context.pages[-1]

    async def navigate(self, runtime_id: str, action: str, url: str | None) -> None:
        from playwright.async_api import TimeoutError as PlaywrightTimeout

        page = self._page(runtime_id)
        try:
            if action == "back":
                await page.go_back(wait_until="commit", timeout=15_000)
            elif action == "forward":
                await page.go_forward(wait_until="commit", timeout=15_000)
            elif action == "reload":
                await page.reload(wait_until="commit", timeout=15_000)
            elif action == "goto" and url:
                await page.goto(url, wait_until="commit", timeout=15_000)
            else:
                raise ValueError(f"unsupported navigation: {action}")
        except PlaywrightTimeout:
            log.info("navigation timed out action=%s", action)

    async def shutdown(self) -> None:
        for runtime_id in list(self._instances):
            await self._teardown(runtime_id)
        if self._pw is not None:
            with contextlib.suppress(Exception):
                await self._pw.stop()
            self._pw = None
