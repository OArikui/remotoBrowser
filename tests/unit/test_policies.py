from __future__ import annotations

import pytest

from package.browser.policies import (
    UrlNotAllowed,
    build_url_checker,
    check_url,
    check_websocket_url,
    is_public_ip,
    normalize_url,
    parse_allowed_hosts,
)
from tests.conftest import fake_resolver


async def _check(url: str) -> None:
    await check_url(url, resolver=fake_resolver)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://10.1.2.3/",
        "http://192.168.0.1:8080/",
        "http://172.16.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.64.0.1/",
        "http://0.0.0.0/",
        "http://[::ffff:127.0.0.1]/",
        "http://localhost/",
        "http://internal.example/",
        "http://rebind.example/",  # 公開IPと内部IPの両方に解決されるホストも拒否
        "http://unknown.invalid/",
        "file:///etc/passwd",
        "ftp://example.com/",
        "javascript:alert(1)",
        "http://user:pw@example.com/",
        "http://example.com:8080/",
        "http://example.com:0/",
        "https:///nohost",
        "http://[::1",
    ],
)
async def test_blocked_urls(url: str) -> None:
    with pytest.raises(UrlNotAllowed):
        await _check(url)


@pytest.mark.parametrize(
    "url",
    ["https://example.com/path?q=1", "http://93.184.216.34/"],
)
async def test_allowed_urls(url: str) -> None:
    await _check(url)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("example.com", "https://example.com"),
        ("  http://example.com/a ", "http://example.com/a"),
        ("example.com/x?y=1", "https://example.com/x?y=1"),
    ],
)
def test_normalize_url(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "x" * 3000])
def test_normalize_url_rejects(raw: str) -> None:
    with pytest.raises(UrlNotAllowed):
        normalize_url(raw)


def test_is_public_ip() -> None:
    assert is_public_ip("93.184.216.34")
    assert not is_public_ip("fe80::1%eth0")
    assert not is_public_ip("not-an-ip")


async def test_exact_host_allowlist_and_websocket_policy() -> None:
    checker = build_url_checker(["example.com"], resolver=fake_resolver)
    await checker("https://example.com/owned-app")
    await check_websocket_url("wss://example.com/socket", checker)

    for url in (
        "https://www.example.com/",
        "https://example.com.evil.invalid/",
        "https://evil.example.com/",
        "https://internal.example/",
        "https://example.com:8443/",
        "wss://localhost/socket",
    ):
        with pytest.raises(UrlNotAllowed):
            if url.startswith("ws"):
                await check_websocket_url(url, checker)
            else:
                await checker(url)


def test_allowed_hosts_reject_wildcards_and_urls() -> None:
    assert parse_allowed_hosts("Example.com, example.org.") == {
        "example.com",
        "example.org",
    }
    for invalid in ("*.example.com", "https://example.com", "example.com:443", "127.0.0.1"):
        with pytest.raises(ValueError):
            parse_allowed_hosts(invalid)


def test_production_settings_require_https_access_controls() -> None:
    from pydantic import ValidationError

    from package.config import Settings

    base = {
        "app_env": "production",
        "app_secret_key": "s" * 48,
        "base_url": "https://browser.example.org",
        "discord_client_id": "client-id",
        "discord_client_secret": "client-secret",
        "allowed_discord_ids": "123456789012345678",
        "browser_allowed_hosts": "owned.example.org,static.owned.example.org",
        "default_start_url": "https://owned.example.org/",
        "browser_runtime": "process",
        "enable_docs": False,
    }
    Settings(_env_file=None, **base)  # pyright: ignore[reportCallIssue]

    for changes in (
        {"base_url": "http://browser.example.org"},
        {"allowed_discord_ids": ""},
        {"browser_allowed_hosts": ""},
        {"default_start_url": "https://other.example.org"},
        {"enable_docs": True},
    ):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **(base | changes))  # pyright: ignore[reportCallIssue]
