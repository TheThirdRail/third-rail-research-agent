"""Utilities for LM Studio endpoint and auth normalization."""

from __future__ import annotations

LMSTUDIO_DEFAULT_API_KEY = "lm-studio"


def normalize_lmstudio_base_url(
    base_url: str | None, *, include_v1: bool = True
) -> str:
    """Normalize LM Studio base URL.

    Args:
        base_url: Raw base URL from settings/env.
        include_v1: Whether the returned URL should end in ``/v1``.

    Returns:
        Normalized base URL string, or an empty string if input is missing.
    """
    normalized = (base_url or "").strip().rstrip("/")
    if not normalized:
        return ""

    if include_v1:
        return normalized if normalized.endswith("/v1") else f"{normalized}/v1"

    if normalized.endswith("/v1"):
        return normalized[:-3].rstrip("/")
    return normalized


def lmstudio_model_endpoints(base_url: str | None) -> list[str]:
    """Return model-list endpoints for LM Studio, preferring OpenAI-compatible paths."""
    root = normalize_lmstudio_base_url(base_url, include_v1=False)
    if not root:
        return []
    return [f"{root}/v1/models", f"{root}/models"]


def resolve_lmstudio_api_key(*candidates: str | None) -> str:
    """Resolve LM Studio API key with a safe non-empty fallback token."""
    for candidate in candidates:
        if candidate and candidate.strip():
            return candidate.strip()
    return LMSTUDIO_DEFAULT_API_KEY
