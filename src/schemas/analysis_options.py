"""Per-run analysis options.

Allows CLI/API callers to override important analysis behavior
per run. Defaults work without passing options.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnalysisOptions(BaseModel):
    """Configurable options for a single analysis run.

    All fields are optional; when omitted, the system defaults
    from ``Settings`` (environment / config) are used instead.
    """

    strict_bucket_enforcement: bool | None = Field(
        default=None,
        description="Require all configured bucket groups to be filled.",
    )
    required_bucket_groups: list[str] | None = Field(
        default=None,
        description="Override which bucket groups are required (e.g., ['left_side', 'right_side']).",
    )
    preferred_bucket_groups: list[str] | None = Field(
        default=None,
        description="Override which bucket groups are preferred but optional.",
    )
    enable_semantic_memory: bool | None = Field(
        default=None,
        description="Enable semantic memory indexing for this run.",
    )
    enable_semantic_candidate_scoring: bool | None = Field(
        default=None,
        description="Enable semantic candidate scoring for this run.",
    )
    enable_semantic_query_expansion: bool | None = Field(
        default=None,
        description="Enable LLM-based semantic query expansion.",
    )
    enable_visual_evidence_resolution: bool | None = Field(
        default=None,
        description="Enable visual evidence resolution for this run.",
    )
    enable_screenshot_capture: bool | None = Field(
        default=None,
        description="Enable screenshot capture for this run.",
    )
    embedding_provider: str | None = Field(
        default=None,
        description="Embedding provider to use (e.g., 'lmstudio', 'fake').",
    )
    embedding_model: str | None = Field(
        default=None,
        description="Embedding model to use (e.g., 'qwen3-embedding-8b').",
    )
    vector_store: str | None = Field(
        default=None,
        description="Vector store backend (e.g., 'lancedb', 'none').",
    )
