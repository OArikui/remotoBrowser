"""ブラウザが開いてよいURLのポリシー(SSRF対策の第一層)。

URL文字列の検査だけでは不十分(DNS再解決・リダイレクト・DNS rebinding)なので、
`lifecycle.py` ではブラウザが発行する全リクエストにも同じ検査を適用する。
最終的な境界はコンテナのネットワーク制限(外部のみ許可)で担保すること。
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

MAX_URL_LENGTH = 2048
NETWORK_SCHEMES = frozenset({"http", "https"})

Resolver = Callable[[str, int], Awaitable[list[str]]]
UrlChecker = Callable[[str], Awaitable[None]]


class UrlNotAllowed(ValueError):
    """リモートブラウザに開かせてはいけないURL。"""


async def resolve_host(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UrlNotAllowed(f"cannot resolve host: {host}") from exc
    return sorted({str(info[4][0]) for info in infos})


def is_public_ip(value: str) -> bool:
    try:
        addr = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


def normalize_url(raw: str) -> str:
    url = raw.strip()
    if not url:
        raise UrlNotAllowed("URL is empty")
    if len(url) > MAX_URL_LENGTH:
        raise UrlNotAllowed("URL is too long")
    if "://" not in url:
        url = "https://" + url
    return url


async def check_url(url: str, resolver: Resolver = resolve_host) -> None:
    """許可されないURLなら UrlNotAllowed を送出する。"""
    parts = urlsplit(url)
    if parts.scheme not in NETWORK_SCHEMES:
        raise UrlNotAllowed("only http and https URLs are allowed")
    if parts.username or parts.password:
        raise UrlNotAllowed("URLs with embedded credentials are not allowed")
    host = parts.hostname
    if not host:
        raise UrlNotAllowed("URL has no host")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise UrlNotAllowed("invalid port") from exc

    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        addresses = await resolver(host, port)

    if not addresses:
        raise UrlNotAllowed("host did not resolve")
    for address in addresses:
        if not is_public_ip(address):
            raise UrlNotAllowed("destination is not a public address")
