"""Shared FastAPI dependencies for the Research Agent API."""

import secrets
from collections.abc import AsyncGenerator
from threading import BoundedSemaphore, Lock

from fastapi import Header, HTTPException, status

from src.core import config as _cfg

_expensive_endpoint_lock = Lock()
_expensive_endpoint_semaphore: BoundedSemaphore | None = None
_expensive_endpoint_limit: int | None = None


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


def _get_expensive_endpoint_semaphore() -> BoundedSemaphore:
    global _expensive_endpoint_limit, _expensive_endpoint_semaphore

    limit = max(1, _cfg.settings.expensive_endpoint_concurrency_limit)
    with _expensive_endpoint_lock:
        if _expensive_endpoint_semaphore is None or _expensive_endpoint_limit != limit:
            _expensive_endpoint_semaphore = BoundedSemaphore(limit)
            _expensive_endpoint_limit = limit
        return _expensive_endpoint_semaphore


async def require_expensive_endpoint_slot() -> AsyncGenerator[None, None]:
    """Reject expensive endpoint calls when the process-local limit is saturated."""
    semaphore = _get_expensive_endpoint_semaphore()
    if not semaphore.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Expensive endpoint concurrency limit exceeded.",
        )
    try:
        yield
    finally:
        semaphore.release()
