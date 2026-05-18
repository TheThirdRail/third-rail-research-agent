"""Time helpers shared by persistence and diagnostics code."""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now_naive() -> datetime:
    """Return current UTC time as a naive datetime for existing DB columns."""
    return datetime.now(UTC).replace(tzinfo=None)


def to_utc_naive(value: datetime) -> datetime:
    """Normalize aware datetimes to naive UTC for existing DB-style comparisons."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)
