"""URL utility functions shared across tools and services."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeUrlError(ValueError):
    """Raised when a content URL targets a non-public destination."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


_NON_HTTP_REASON = "blocked_non_http_url"
_CREDENTIALS_REASON = "blocked_url_with_credentials"
_PRIVATE_REASON = "blocked_private_or_local_url"
_DNS_FAILURE_REASON = "hostname_resolution_failed"
_METADATA_HOSTS = {"169.254.169.254", "fd00:ec2::254"}


def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication without changing fetch semantics."""
    if not url:
        return ""

    text = url.strip()
    try:
        parsed = urlparse(text)
        if parsed.scheme and parsed.netloc:
            path = parsed.path.rstrip("/")
            return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"
    except ValueError:
        pass

    return text.lower().rstrip("/")


def extract_domain(url_or_domain: str) -> str:
    """Extract a normalised domain from a URL or bare domain string.

    Handles full URLs, bare domains, ``www.`` prefixes, and invalid input.

    Returns:
        Lower-cased domain with leading ``www.`` stripped, or the cleaned
        input string if parsing fails.
    """
    if not url_or_domain:
        return ""

    text = url_or_domain.strip()

    # If it looks like a URL, parse it.
    if "://" in text or text.startswith("//"):
        try:
            host = urlparse(text).netloc
            if host:
                return host.lower().removeprefix("www.")
        except ValueError:
            return text.lower().removeprefix("www.")

    return text.lower().removeprefix("www.")


def validate_public_http_url(url: str, *, resolve_dns: bool = True) -> str:
    """Return the stripped URL only when it targets a public HTTP(S) host."""
    reason = blocked_public_url_reason(url, resolve_dns=resolve_dns)
    if reason:
        raise UnsafeUrlError(reason)
    return url.strip()


def blocked_public_url_reason(url: str, *, resolve_dns: bool = True) -> str:
    """Return a stable block reason for unsafe content URLs, or ``""``."""
    if not url:
        return _NON_HTTP_REASON

    text = url.strip()
    try:
        parsed = urlparse(text)
        _ = parsed.port
    except ValueError:
        return _NON_HTTP_REASON

    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return _NON_HTTP_REASON
    if parsed.username is not None or parsed.password is not None:
        return _CREDENTIALS_REASON

    hostname = parsed.hostname.strip().lower().rstrip(".")
    if _is_blocked_hostname(hostname):
        return _PRIVATE_REASON

    literal_ip = _parse_ip_address(hostname)
    if literal_ip is not None:
        return _PRIVATE_REASON if _is_blocked_ip(literal_ip) else ""

    if not resolve_dns:
        return ""

    try:
        resolved_ips = _resolve_host_ips(hostname)
    except OSError:
        return _DNS_FAILURE_REASON

    if not resolved_ips:
        return _DNS_FAILURE_REASON
    if any(_is_blocked_ip(ip) for ip in resolved_ips):
        return _PRIVATE_REASON

    return ""


def _is_blocked_hostname(hostname: str) -> bool:
    return (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname in _METADATA_HOSTS
    )


def _resolve_host_ips(
    hostname: str,
) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for addr in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM):
        ip = _parse_ip_address(addr[4][0])
        if ip is not None and ip not in addresses:
            addresses.append(ip)
    return addresses


def _parse_ip_address(
    value: str,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return None


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        not ip.is_global
        or ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    )
