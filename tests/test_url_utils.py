import socket

import pytest

from src.utils.url_utils import (
    UnsafeUrlError,
    blocked_public_url_reason,
    normalize_url,
    validate_public_http_url,
)


def _fake_addrinfo(*addresses: str):
    return [
        (
            socket.AF_INET6 if ":" in address else socket.AF_INET,
            socket.SOCK_STREAM,
            0,
            "",
            (address, 443),
        )
        for address in addresses
    ]


def test_normalize_url_preserves_existing_dedupe_shape():
    assert normalize_url("HTTPS://Example.COM/path/?a=1#frag") == (
        "https://example.com/path"
    )
    assert normalize_url("example.com/Story/") == "example.com/story"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/internal",
        "http://localhost:8000/internal",
        "http://service.localhost/internal",
        "http://10.0.0.1/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data/",
        "http://169.254.1.20/",
        "http://224.0.0.1/",
    ],
)
def test_blocks_literal_private_local_link_local_and_multicast_urls(url: str):
    assert blocked_public_url_reason(url, resolve_dns=False) == (
        "blocked_private_or_local_url"
    )
    with pytest.raises(UnsafeUrlError) as exc_info:
        validate_public_http_url(url, resolve_dns=False)
    assert exc_info.value.reason == "blocked_private_or_local_url"


@pytest.mark.parametrize(
    "url,reason",
    [
        ("file:///etc/passwd", "blocked_non_http_url"),
        ("http://example.com:bad-port/story", "blocked_non_http_url"),
        ("https://user:pass@example.com/story", "blocked_url_with_credentials"),
        ("https:///missing-host", "blocked_non_http_url"),
    ],
)
def test_blocks_non_content_url_shapes(url: str, reason: str):
    assert blocked_public_url_reason(url, resolve_dns=False) == reason


def test_blocks_hostname_that_resolves_to_private_ip(monkeypatch):
    monkeypatch.setattr(
        "src.utils.url_utils.socket.getaddrinfo",
        lambda *args, **kwargs: _fake_addrinfo("10.0.0.5"),
    )

    assert blocked_public_url_reason("https://news.example/story") == (
        "blocked_private_or_local_url"
    )


def test_allows_public_hostname_with_public_resolution(monkeypatch):
    monkeypatch.setattr(
        "src.utils.url_utils.socket.getaddrinfo",
        lambda *args, **kwargs: _fake_addrinfo("93.184.216.34"),
    )

    assert (
        validate_public_http_url("https://example.com/story")
        == "https://example.com/story"
    )


def test_fails_closed_when_dns_resolution_fails(monkeypatch):
    def fail_resolution(*args, **kwargs):
        raise OSError("no dns")

    monkeypatch.setattr("src.utils.url_utils.socket.getaddrinfo", fail_resolution)

    with pytest.raises(UnsafeUrlError) as exc_info:
        validate_public_http_url("https://missing.example/story")
    assert exc_info.value.reason == "hostname_resolution_failed"
