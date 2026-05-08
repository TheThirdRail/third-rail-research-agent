"""Shared FastAPI dependencies for the Research Agent API."""

import secrets

from fastapi import Header, HTTPException, status

from src.core import config as _cfg


def require_admin_api_key(
    x_research_agent_key: str | None = Header(default=None),
) -> None:
    """Reject requests that lack a valid admin API key.

    When ``ADMIN_API_KEY`` is empty the admin surface is disabled entirely
    and every protected route returns 503.
    """
    expected = _cfg.settings.admin_api_key.strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API is not configured.",
        )
    if not secrets.compare_digest(x_research_agent_key or "", expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized.",
        )
