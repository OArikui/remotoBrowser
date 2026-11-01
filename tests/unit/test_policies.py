from __future__ import annotations

import pytest

from package.browser.policies import UrlNotAllowed, check_url, is_public_ip, normalize_url
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
        "https:///nohost",
    ],
)
async def test_blocked_urls(url: str) -> None:
    with pytest.raises(UrlNotAllowed):
        await _check(url)


@pytest.mark.parametrize(
    "url",
    ["https://example.com/path?q=1", "http://example.com:8080/", "http://93.184.216.34/"],
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
