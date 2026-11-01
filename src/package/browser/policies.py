"""ブラウザの接続先を管理対象ホストへ限定するポリシー。

URLの完全一致ホスト許可リストに加え、DNS解決結果がすべてグローバルIPであることを
確認する。DNS再解決などの競合を完全には防げないため、OCI本番環境では
`deployment/oci/remotobrowser-egress-filter.sh` によるコンテナ出口制限も併用する。
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable, Iterable
from urllib.parse import urlsplit, urlunsplit

MAX_URL_LENGTH = 2048
NETWORK_SCHEMES = frozenset({"http", "https"})
WEBSOCKET_SCHEMES = frozenset({"ws", "wss"})
ALLOWED_WEB_PORTS = frozenset({80, 443})

Resolver = Callable[[str, int], Awaitable[list[str]]]
UrlChecker = Callable[[str], Awaitable[None]]
_HOST_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class UrlNotAllowed(ValueError):
    """管理対象として許可されていない接続先。"""


def normalize_hostname(value: str) -> str:
    """DNSホスト名を小文字ASCII(IDNA)へ正規化する。IPアドレスは受け付けない。"""
    host = value.strip().rstrip(".").lower()
    if not host or "*" in host or ":" in host:
        raise ValueError(f"invalid hostname: {value!r}")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP addresses cannot be added to the browser host allowlist")

    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError(f"invalid hostname: {value!r}") from exc

    if len(ascii_host) > 253:
        raise ValueError("hostname is too long")
    labels = ascii_host.split(".")
    if len(labels) < 2 or any(not _HOST_LABEL_RE.fullmatch(label) for label in labels):
        raise ValueError(f"invalid DNS hostname: {value!r}")
    return ascii_host


def parse_allowed_hosts(value: str | Iterable[str]) -> frozenset[str]:
    """カンマ区切り文字列または文字列群を完全一致許可リストに変換する。

    ワイルドカード・URLスキーム・ポート・IPアドレスは拒否する。
    """
    values = value.split(",") if isinstance(value, str) else list(value)
    hosts = frozenset(normalize_hostname(item) for item in values if item.strip())
    if len(hosts) > 100:
        raise ValueError("BROWSER_ALLOWED_HOSTS may contain at most 100 hostnames")
    return hosts


async def resolve_host(host: str, port: int) -> list[str]:
    """ホスト名を解決し、返された全IPを文字列で返す。"""
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(host, port, type=socket.SOCK_STREAM), timeout=5.0
        )
    except (OSError, TimeoutError) as exc:
        raise UrlNotAllowed(f"cannot resolve host: {host}") from exc
    return sorted({str(info[4][0]) for info in infos})


def is_public_ip(value: str) -> bool:
    """特殊用途・プライベート・リンクローカルではないグローバルIPか判定する。"""
    try:
        addr = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


def normalize_url(raw: str) -> str:
    """URLを整形し、スキーム省略時はHTTPSを付与する。"""
    url = raw.strip()
    if not url:
        raise UrlNotAllowed("URL is empty")
    if len(url) > MAX_URL_LENGTH:
        raise UrlNotAllowed("URL is too long")
    if "://" not in url:
        url = "https://" + url
    return url


def _http_equivalent(url: str) -> str:
    """WebSocket URLをDNS・IP検査用のHTTP(S) URLへ変換する。"""
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise UrlNotAllowed("invalid WebSocket URL") from exc
    if parts.scheme not in WEBSOCKET_SCHEMES:
        raise UrlNotAllowed("only ws and wss WebSocket destinations are allowed")
    scheme = "https" if parts.scheme == "wss" else "http"
    return urlunsplit((scheme, parts.netloc, parts.path, parts.query, parts.fragment))


async def check_url(url: str, resolver: Resolver = resolve_host) -> None:
    """許可されないURL、または非グローバルIPへ解決されるURLを拒否する。"""
    if len(url) > MAX_URL_LENGTH:
        raise UrlNotAllowed("URL is too long")
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise UrlNotAllowed("invalid URL") from exc
    if parts.scheme not in NETWORK_SCHEMES:
        raise UrlNotAllowed("only http and https URLs are allowed")
    if parts.username or parts.password:
        raise UrlNotAllowed("URLs with embedded credentials are not allowed")
    host = parts.hostname
    if not host:
        raise UrlNotAllowed("URL has no host")
    try:
        port = parts.port if parts.port is not None else (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise UrlNotAllowed("invalid port") from exc
    if port not in ALLOWED_WEB_PORTS:
        raise UrlNotAllowed("only ports 80 and 443 are allowed")

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


def build_url_checker(
    allowed_hosts: Iterable[str],
    resolver: Resolver = resolve_host,
) -> UrlChecker:
    """完全一致のホスト許可リストとDNS/IP検査を組み合わせたチェッカーを返す。"""
    hosts = parse_allowed_hosts(allowed_hosts)

    async def checker(url: str) -> None:
        try:
            parts = urlsplit(url)
        except ValueError as exc:
            raise UrlNotAllowed("invalid URL") from exc
        host = parts.hostname
        if not host:
            raise UrlNotAllowed("URL has no host")
        try:
            normalized = normalize_hostname(host)
        except ValueError as exc:
            raise UrlNotAllowed("destination hostname is not allowed") from exc
        if normalized not in hosts:
            raise UrlNotAllowed("destination host is not in BROWSER_ALLOWED_HOSTS")
        await check_url(url, resolver=resolver)

    return checker


async def check_websocket_url(url: str, checker: UrlChecker) -> None:
    """通常のURLチェッカーを使ってWebSocketの宛先を検査する。"""
    await checker(_http_equivalent(url))
