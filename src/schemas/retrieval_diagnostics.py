"""Schemas for retrieval candidate lifecycle diagnostics."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.core.time_utils import utc_now_naive

CandidateStage = Literal["primary", "rss", "site_search", "open_web", "unknown"]
CandidateState = Literal[
    "discovered",
    "extraction_failed",
    "extracted",
    "relevance_rejected",
    "duplicate_rejected",
    "policy_rejected",
    "retained",
]


class CandidateDecision(BaseModel):
    """Terminal lifecycle decision for a probed retrieval candidate."""

    url: str
    domain: str = ""
    title: str = ""
    stage: CandidateStage = "unknown"
    state: CandidateState
    bucket_label: str | None = None
    exact_bias: int | None = None
    rejection_reason: str | None = None
    extraction_error: str | None = None
    extraction_error_code: str | None = None
    extractor_method: str | None = None
    http_status: int | None = None
    relevance_score: float | None = None
    relevance_diagnostics: dict[str, Any] = Field(default_factory=dict)
    source_score: float | None = None
    media_diagnostics: dict[str, Any] = Field(default_factory=dict)
    discovered_at: datetime = Field(default_factory=utc_now_naive)


class RelevanceDiagnostics(BaseModel):
    """Persistable relevance score breakdown for one candidate."""

    total: float
    entity_overlap: float
    event_overlap: float
    time_overlap: float
    place_overlap: float
    topic_match: float
    novelty: float
    semantic_similarity: float | None = None
    semantic_chunk_similarity: float | None = None
    distinctive_term_overlap: float
    direct_evidence_score: float
    coverage_type: str
    rejection_reason: str | None = None


class MissingBucketExplanation(BaseModel):
    """Why a required retrieval bucket was not filled."""

    bucket_label: str
    reason: str
    probed_count: int = 0
    by_state: dict[str, int] = Field(default_factory=dict)
    rejection_reasons: dict[str, int] = Field(default_factory=dict)
    probe_limit_reached: bool = False


class BucketLaneAttempt(BaseModel):
    """Search/probe attempt for one planned bucket lane."""

    bucket_label: str
    stage: CandidateStage
    query: str = ""
    query_family: str | None = None
    exact_bias: int | None = None
    domains: list[str] = Field(default_factory=list)
    result_count: int = 0
    new_result_count: int = 0
    exhausted_reason: str | None = None


class CandidateCensus(BaseModel):
    """Aggregate lifecycle counts for an analysis retrieval run."""

    total: int = 0
    by_state: dict[str, int] = Field(default_factory=dict)
    by_stage: dict[str, int] = Field(default_factory=dict)
    by_bucket: dict[str, int] = Field(default_factory=dict)
    missing_buckets: list[str] = Field(default_factory=list)
    missing_bucket_explanations: list[MissingBucketExplanation] = Field(
        default_factory=list
    )
    bucket_lane_attempts: list[BucketLaneAttempt] = Field(default_factory=list)

    @classmethod
    def from_decisions(
        cls,
        decisions: list[CandidateDecision],
        *,
        missing_buckets: list[str] | None = None,
        missing_bucket_explanations: list[MissingBucketExplanation] | None = None,
        bucket_lane_attempts: list[BucketLaneAttempt] | None = None,
    ) -> CandidateCensus:
        state_counts = Counter(decision.state for decision in decisions)
        stage_counts = Counter(decision.stage for decision in decisions)
        bucket_counts = Counter(
            decision.bucket_label for decision in decisions if decision.bucket_label
        )
        return cls(
            total=len(decisions),
            by_state={str(state): count for state, count in state_counts.items()},
            by_stage={str(stage): count for stage, count in stage_counts.items()},
            by_bucket=dict(bucket_counts),
            missing_buckets=list(missing_buckets or []),
            missing_bucket_explanations=list(missing_bucket_explanations or []),
            bucket_lane_attempts=list(bucket_lane_attempts or []),
        )
