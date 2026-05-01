"""Structured observability events for the analysis pipeline.

Emits structured log events at key pipeline stages to support
operational monitoring, debugging, and future metrics collection.

Each event function logs a structured JSON payload via Python logging.
Events use the ``analysis.*`` namespace for consistent filtering.
"""

import logging
import time
from collections import Counter
from typing import Any

logger = logging.getLogger("analysis.events")


def _emit(event_name: str, payload: dict[str, Any]) -> None:
    """Emit a structured event as an INFO-level log record.

    The record includes the event name in the message and the full
    payload as the ``event_data`` extra field for structured log
    processors (e.g. JSON formatters, log aggregators).
    """
    logger.info(
        "%s %s",
        event_name,
        payload,
        extra={"event_name": event_name, "event_data": payload},
    )


def run_started(
    *,
    story_id: str,
    description: str,
    url: str | None,
) -> float:
    """Emit ``analysis.run_started`` and return a monotonic start timestamp.

    Returns:
        Monotonic clock value to pass to :func:`run_completed`.
    """
    start = time.monotonic()
    _emit(
        "analysis.run_started",
        {
            "story_id": story_id,
            "description": description[:120],
            "url": url or "",
        },
    )
    return start


def run_completed(
    *,
    story_id: str,
    status: str,
    start_time: float,
    source_count: int,
    warnings_count: int,
) -> None:
    """Emit ``analysis.run_completed`` with elapsed time."""
    _emit(
        "analysis.run_completed",
        {
            "story_id": story_id,
            "status": status,
            "elapsed_seconds": round(time.monotonic() - start_time, 2),
            "source_count": source_count,
            "warnings_count": warnings_count,
        },
    )


def bucket_probe_started(
    *,
    story_id: str,
    bucket_label: str,
    stage: str,
    exact_bias: int | None = None,
    query: str = "",
    domains: list[str] | None = None,
) -> None:
    """Emit ``analysis.bucket_probe_started``."""
    _emit(
        "analysis.bucket_probe_started",
        {
            "story_id": story_id,
            "bucket_label": bucket_label,
            "stage": stage,
            "exact_bias": exact_bias,
            "query": query[:200],
            "domains": (domains or [])[:10],
        },
    )


def candidate_totals(
    *,
    story_id: str,
    candidate_decisions: list[Any],
) -> None:
    """Emit aggregate candidate lifecycle counts.

    Emits:
        - ``analysis.candidate_discovered_total``
        - ``analysis.candidate_extracted_total``
        - ``analysis.candidate_rejected_total``
    """
    state_counts = Counter(getattr(d, "state", "unknown") for d in candidate_decisions)
    rejection_counts = Counter(
        getattr(d, "rejection_reason", "unknown") or "unknown"
        for d in candidate_decisions
        if getattr(d, "state", "")
        in (
            "relevance_rejected",
            "duplicate_rejected",
            "policy_rejected",
        )
    )

    discovered = len(candidate_decisions)
    extracted = sum(
        1
        for d in candidate_decisions
        if getattr(d, "state", "") not in ("discovered", "extraction_failed")
    )
    rejected = sum(
        1 for d in candidate_decisions if getattr(d, "state", "").endswith("_rejected")
    )

    _emit(
        "analysis.candidate_discovered_total",
        {"story_id": story_id, "total": discovered, "by_state": dict(state_counts)},
    )
    _emit(
        "analysis.candidate_extracted_total",
        {"story_id": story_id, "total": extracted},
    )
    _emit(
        "analysis.candidate_rejected_total",
        {
            "story_id": story_id,
            "total": rejected,
            "by_reason": dict(rejection_counts),
        },
    )


def bucket_fill_ratio(
    *,
    story_id: str,
    coverage: dict[str, Any],
) -> None:
    """Emit ``analysis.bucket_fill_ratio`` for each required bucket."""
    retained = int(coverage.get("retained_count", 0))
    probed = int(coverage.get("probed_count", 0))
    missing = coverage.get("missing_buckets", [])

    bucket_ratios: dict[str, dict[str, Any]] = {}
    for label in ("left_side", "center", "right_side"):
        count_key = {
            "left_side": "left_count",
            "center": "center_count",
            "right_side": "right_count",
        }[label]
        count = int(coverage.get(count_key, 0))
        bucket_ratios[label] = {
            "count": count,
            "filled": count > 0,
            "missing": label in missing,
        }

    _emit(
        "analysis.bucket_fill_ratio",
        {
            "story_id": story_id,
            "retained": retained,
            "probed": probed,
            "buckets": bucket_ratios,
        },
    )


def rss_precision_at_accept(
    *,
    story_id: str,
    rss_candidates: int,
    rss_accepted: int,
) -> None:
    """Emit ``analysis.rss_precision_at_accept``."""
    precision = rss_accepted / rss_candidates if rss_candidates > 0 else 0.0
    _emit(
        "analysis.rss_precision_at_accept",
        {
            "story_id": story_id,
            "rss_candidates": rss_candidates,
            "rss_accepted": rss_accepted,
            "precision": round(precision, 3),
        },
    )


def semantic_memory_chunks_total(
    *,
    story_id: str,
    chunks: int,
    documents: int,
) -> None:
    """Emit ``analysis.semantic_memory_chunks_total``."""
    _emit(
        "analysis.semantic_memory_chunks_total",
        {
            "story_id": story_id,
            "chunks": chunks,
            "documents": documents,
        },
    )


def social_post_resolve_result(
    *,
    story_id: str,
    total: int,
    success: int,
    fallback: int,
) -> None:
    """Emit social post resolve and visual fallback totals.

    Emits:
        - ``analysis.social_post_resolve_success_total``
        - ``analysis.visual_fallback_total``
    """
    _emit(
        "analysis.social_post_resolve_success_total",
        {
            "story_id": story_id,
            "total": total,
            "success": success,
        },
    )
    _emit(
        "analysis.visual_fallback_total",
        {
            "story_id": story_id,
            "total": total,
            "fallback": fallback,
        },
    )


def source_matrix_missing_key_framing(
    *,
    story_id: str,
    total_sources: int,
    missing_count: int,
) -> None:
    """Emit ``analysis.source_matrix_missing_key_framing_total``."""
    _emit(
        "analysis.source_matrix_missing_key_framing_total",
        {
            "story_id": story_id,
            "total_sources": total_sources,
            "missing_count": missing_count,
        },
    )


def report_validation_warnings(
    *,
    story_id: str,
    warnings: list[str],
) -> None:
    """Emit ``analysis.report_validation_warning_total``."""
    type_counts: dict[str, int] = {}
    for warning in warnings:
        # Classify warning type from message prefix
        if "orphan" in warning.lower():
            wtype = "orphaned_citation"
        elif "evidence" in warning.lower() or "limitation" in warning.lower():
            wtype = "evidence_limitation"
        elif "missing" in warning.lower() and "bucket" in warning.lower():
            wtype = "missing_bucket"
        elif "source" in warning.lower():
            wtype = "source_validation"
        else:
            wtype = "other"
        type_counts[wtype] = type_counts.get(wtype, 0) + 1

    _emit(
        "analysis.report_validation_warning_total",
        {
            "story_id": story_id,
            "total": len(warnings),
            "by_type": type_counts,
        },
    )
