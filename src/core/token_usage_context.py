"""Context helpers for attaching run metadata to LLM token usage records."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TokenUsageRunContext:
    """Logical analysis run metadata propagated to LLM calls."""

    run_id: str | None = None
    run_text: str | None = None


_current_run: ContextVar[TokenUsageRunContext | None] = ContextVar(
    "token_usage_run_context",
    default=None,
)

_AGENT_DISPLAY_NAME_OVERRIDES = {
    "semantic_query_expander": "STORY_PARSER",
}


def token_usage_agent_display_name(agent_name: str | None) -> str | None:
    if not agent_name:
        return None
    key = agent_name.strip().lower().replace("-", "_").replace(" ", "_")
    if not key:
        return None
    return _AGENT_DISPLAY_NAME_OVERRIDES.get(key, key.upper())


@contextmanager
def token_usage_run(run_id: str, run_text: str):
    """Temporarily set token-usage metadata for the current analysis run."""
    token = _current_run.set(TokenUsageRunContext(run_id=run_id, run_text=run_text))
    try:
        yield
    finally:
        _current_run.reset(token)


def current_token_usage_metadata(agent_name: str | None = None) -> dict[str, Any]:
    """Return metadata that should be attached to the next LLM call."""
    context = _current_run.get() or TokenUsageRunContext()
    metadata: dict[str, Any] = {}
    if context.run_id:
        metadata["run_id"] = context.run_id
    if context.run_text:
        metadata["run_text"] = context.run_text
    display_name = token_usage_agent_display_name(agent_name)
    if display_name:
        metadata["agent_name"] = display_name
    return metadata


def merge_token_usage_metadata(
    kwargs: dict[str, Any],
    *,
    agent_name: str | None = None,
) -> dict[str, Any]:
    """Merge current token-usage metadata into OpenAI-compatible extra_body."""
    metadata = current_token_usage_metadata(agent_name=agent_name)
    if not metadata:
        return kwargs

    merged = dict(kwargs)
    extra_body = merged.get("extra_body")
    extra_body = dict(extra_body) if isinstance(extra_body, dict) else {}
    existing_metadata = extra_body.get("metadata")
    if isinstance(existing_metadata, dict):
        extra_body["metadata"] = {**metadata, **existing_metadata}
    else:
        extra_body["metadata"] = metadata
    merged["extra_body"] = extra_body
    return merged
