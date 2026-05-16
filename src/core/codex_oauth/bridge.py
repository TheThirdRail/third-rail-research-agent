"""Diagnostics for Codex OAuth OpenAI-compatible bridge mode."""

from __future__ import annotations

import os
from typing import Any

from src.core.codex_oauth.safety import (
    CodexOAuthConfigError,
    is_local_bridge_url,
    redact_secrets,
    validate_bridge_url,
)

BRIDGE_MODE = "openai_compatible_bridge"


def configured_openai_base_url(settings: Any) -> str:
    """Resolve the OpenAI-compatible base URL from env or settings."""
    return str(
        os.getenv("OPENAI_BASE_URL") or getattr(settings, "openai_base_url", "") or ""
    )


def validate_bridge_mode(
    settings: Any,
    *,
    provider: str | None = None,
    require_settings_provider: bool = True,
) -> None:
    """Validate bridge mode without duplicating LiteLLM completion logic."""
    mode = getattr(settings, "codex_oauth_mode", "disabled")
    if mode != BRIDGE_MODE:
        raise CodexOAuthConfigError(
            "CODEX_OAUTH_MODE must be openai_compatible_bridge for bridge mode."
        )

    provider_name = (
        str(provider or getattr(settings, "llm_provider", "") or "").strip().lower()
    )
    if require_settings_provider and provider_name != "openai":
        raise CodexOAuthConfigError(
            "Bridge mode requires LLM_PROVIDER=openai to reuse the OpenAI-compatible path."
        )

    base_url = configured_openai_base_url(settings)
    validate_bridge_url(
        base_url,
        require_localhost=getattr(settings, "codex_require_localhost", True),
        allow_public_api=getattr(settings, "codex_allow_public_api", False),
    )

    if not (os.getenv("OPENAI_API_KEY") or getattr(settings, "openai_api_key", "")):
        raise CodexOAuthConfigError(
            "OPENAI_API_KEY is required for the OpenAI-compatible bridge; use a "
            "local placeholder if the bridge ignores it."
        )


def diagnose_bridge(settings: Any) -> dict[str, Any]:
    """Return bridge configuration diagnostics without exposing credentials."""
    base_url = configured_openai_base_url(settings)
    errors: list[str] = []
    warnings: list[str] = []

    try:
        validate_bridge_url(
            base_url,
            require_localhost=getattr(settings, "codex_require_localhost", True),
            allow_public_api=getattr(settings, "codex_allow_public_api", False),
        )
    except CodexOAuthConfigError as exc:
        errors.append(redact_secrets(exc))

    if getattr(settings, "codex_allow_public_api", False):
        warnings.append("Public API use is enabled; keep this local-only for testing.")
    if not getattr(settings, "codex_require_localhost", True):
        warnings.append("Localhost enforcement is disabled.")
    if getattr(settings, "llm_provider", "").strip().lower() != "openai":
        errors.append("Bridge mode requires LLM_PROVIDER=openai.")
    if not (os.getenv("OPENAI_API_KEY") or getattr(settings, "openai_api_key", "")):
        errors.append("OPENAI_API_KEY is not configured.")

    return {
        "mode": BRIDGE_MODE,
        "openai_base_url_configured": bool(base_url),
        "openai_base_url_local": is_local_bridge_url(base_url),
        "provider_compatible": getattr(settings, "llm_provider", "").strip().lower()
        == "openai",
        "public_api_blocked": not getattr(settings, "codex_allow_public_api", False),
        "safe": not errors,
        "errors": errors,
        "warnings": warnings,
    }
