"""Multi-factor source scoring for balanced source selection.

Replaces generic similarity-only selection with a scoring function
that weighs event similarity, bucket need, source novelty,
factuality, freshness, and duplicate penalty.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.services.source_registry import get_source_registry

logger = logging.getLogger(__name__)


@dataclass
class ScoredCandidate:
    """A source candidate with multi-factor score breakdown."""

    url: str
    domain: str
    title: str
    bias: int
    bucket_label: str
    total_score: float
    event_similarity: float
    similarity_score: float
    bucket_need_score: float
    novelty_score: float
    factuality_score: float
    freshness_score: float
    duplicate_penalty: float


# Factual rating to numeric weight
_FACTUAL_WEIGHTS: dict[str, float] = {
    "very_high": 1.0,
    "high": 0.9,
    "mostly_factual": 0.7,
    "mixed": 0.4,
    "low": 0.2,
    "very_low": 0.1,
}


def score_candidate(
    url: str,
    domain: str,
    title: str,
    bias: int,
    bucket_label: str,
    *,
    similarity: float = 0.5,
    semantic_similarity: float | None = None,
    bucket_is_empty: bool = True,
    domain_already_present: bool = False,
    is_duplicate: bool = False,
    published_date: datetime | None = None,
    reference_date: datetime | None = None,
) -> ScoredCandidate:
    """Score a source candidate using multiple factors.

    Args:
        url: Article URL.
        domain: Source domain.
        title: Article title.
        bias: Bias score (-4 to +4).
        bucket_label: Which bias bucket this source fills.
        similarity: Deterministic/blended fallback event similarity score (0.0-1.0).
        semantic_similarity: Optional semantic event similarity score (0.0-1.0).
        bucket_is_empty: Whether this source's bucket still needs filling.
        domain_already_present: Whether this domain already has a source.
        is_duplicate: Whether this is a detected duplicate.
        published_date: Publication date if known.
        reference_date: Story date for freshness calculation.

    Returns:
        ScoredCandidate with per-factor breakdown and total score.
    """
    registry = get_source_registry()
    entry = registry.lookup_domain(domain)

    # 1) Event similarity (0.0-1.0, weight: 0.25)
    event_similarity = _bounded_score(
        semantic_similarity if semantic_similarity is not None else similarity
    )
    similarity_score = event_similarity * 0.25

    # 2) Bucket need (0.0 or 0.30, weight: 0.30)
    bucket_need_score = 0.30 if bucket_is_empty else 0.05

    # 3) Source novelty (0.0 or 0.15, weight: 0.15)
    novelty_score = 0.0 if domain_already_present else 0.15

    # 4) Factuality (0.0-0.15, weight: 0.15)
    factual_rating = entry.factual_rating if entry else "mixed"
    factuality_score = _FACTUAL_WEIGHTS.get(factual_rating, 0.4) * 0.15

    # 5) Freshness (0.0-0.10, weight: 0.10)
    freshness_score = _compute_freshness(published_date, reference_date) * 0.10

    # 6) Duplicate penalty (0.0 or -0.80)
    duplicate_penalty = -0.80 if is_duplicate else 0.0

    total = max(
        0.0,
        similarity_score
        + bucket_need_score
        + novelty_score
        + factuality_score
        + freshness_score
        + duplicate_penalty,
    )

    return ScoredCandidate(
        url=url,
        domain=domain,
        title=title,
        bias=bias,
        bucket_label=bucket_label,
        total_score=total,
        event_similarity=event_similarity,
        similarity_score=similarity_score,
        bucket_need_score=bucket_need_score,
        novelty_score=novelty_score,
        factuality_score=factuality_score,
        freshness_score=freshness_score,
        duplicate_penalty=duplicate_penalty,
    )


def _bounded_score(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _compute_freshness(
    published_date: datetime | None,
    reference_date: datetime | None,
) -> float:
    """Compute freshness score (0.0-1.0) based on publication recency."""
    if not published_date:
        return 0.5  # Unknown date gets neutral score

    ref = reference_date or datetime.utcnow()
    age = abs((ref - published_date).total_seconds())
    max_age = timedelta(days=30).total_seconds()

    if age <= 0:
        return 1.0
    if age >= max_age:
        return 0.0
    return 1.0 - (age / max_age)
