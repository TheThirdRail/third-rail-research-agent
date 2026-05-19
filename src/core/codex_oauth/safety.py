"""Safety checks for optional local Codex OAuth testing."""

from __future__ import annotations

import re
from urllib.parse import urlparse


class CodexOAuthConfigError(ValueError):
    """Raised when Codex OAuth testing is configured unsafely."""


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
DOCKER_LOCAL_HOSTS = {"host.docker.internal"}
LOCAL_BRIDGE_HOSTS = LOCAL_HOSTS | DOCKER_LOCAL_HOSTS
# These are rejected input hostnames, not bind addresses.
BLOCKED_HOSTS = {"0.0.0.0", "::"}  # nosec B104

_SECRET_PATTERNS = [
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"), True),
    (re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,;]+"), True),
    (re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?[^\n\r,;]+"), True),
    (re.compile(r"(?i)(cookie\s*[:=]\s*)[^\n\r]+"), True),
    (re.compile(r"(?i)(refresh[_-]?token\s*[:=]\s*)[^\s,;]+"), True),
    (re.compile(r"(?i)(access[_-]?token\s*[:=]\s*)[^\s,;]+"), True),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"), False),
    (
        re.compile(r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b"),
        False,
    ),
]


def redact_secrets(value: object) -> str:
    """Return a string safe for diagnostics."""
    text = str(value)
    for pattern, preserve_prefix in _SECRET_PATTERNS:
        if preserve_prefix:
            text = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text


def is_local_bridge_url(url: str) -> bool:
    """Return True when URL targets a local host or Docker host gateway."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    host = parsed.hostname
    return bool(host and host.lower() in LOCAL_BRIDGE_HOSTS)


def validate_bridge_url(
    url: str,
    *,
    require_localhost: bool = True,
    allow_public_api: bool = False,
) -> None:
    """Validate that a bridge URL is present and local unless explicitly allowed."""
    if not url or not url.strip():
        raise CodexOAuthConfigError("OPENAI_BASE_URL is required for bridge mode.")
    if "<" in url or ">" in url:
        raise CodexOAuthConfigError(
            "OPENAI_BASE_URL contains placeholder text; replace it with the "
            "running bridge URL, for example http://host.docker.internal:8790/v1."
        )

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise CodexOAuthConfigError("OPENAI_BASE_URL must be an http(s) URL.")

    host = parsed.hostname.lower()
    try:
        _port = parsed.port
    except ValueError as exc:
        raise CodexOAuthConfigError(
            "OPENAI_BASE_URL has an invalid port; use a numeric port like 8790."
        ) from exc

    if host in BLOCKED_HOSTS:
        raise CodexOAuthConfigError(
            "Bridge URL must not bind to 0.0.0.0 or an unspecified address."
        )

    if require_localhost and not allow_public_api and host not in LOCAL_BRIDGE_HOSTS:
        raise CodexOAuthConfigError(
            "Bridge URL must use localhost, 127.0.0.1, ::1, or "
            "host.docker.internal unless public API access is explicitly enabled."
        )

    if host not in LOCAL_BRIDGE_HOSTS and not (
        allow_public_api and not require_localhost
    ):
        raise CodexOAuthConfigError(
            "Public bridge URLs require CODEX_ALLOW_PUBLIC_API=true and "
            "CODEX_REQUIRE_LOCALHOST=false."
        )


def validate_prompt_length(prompt: str, max_chars: int) -> None:
    """Ensure prompt text stays under the configured local testing limit."""
    if max_chars <= 0:
        raise CodexOAuthConfigError("CODEX_MAX_PROMPT_CHARS must be greater than 0.")
    if len(prompt) > max_chars:
        raise CodexOAuthConfigError(
            f"Prompt is {len(prompt)} characters; limit is {max_chars}."
        )
