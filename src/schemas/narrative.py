"""Pydantic schemas for narrative analysis output."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OpinionCluster(BaseModel):
    """A cluster of opinions from a specific ideological group."""

    bias_group: str = Field(
        description="Ideological group (e.g., 'left', 'right', 'center')"
    )
    key_opinions: list[str] = Field(
        default_factory=list,
        description="Main opinion positions from this group",
    )
    source_ids: list[str] = Field(
        default_factory=list,
        description="Source IDs contributing to these opinions",
    )


class NarrativeResult(BaseModel):
    """Structured output from narrative analysis.

    Separates evidence-derived narrative patterns from
    profile-aware creator angles.
    """

    mainstream_narrative: str = Field(
        default="",
        description="The dominant narrative from mainstream/center sources",
    )
    alternative_narrative: str = Field(
        default="",
        description="Alternative narrative from independent/non-mainstream sources",
    )
    profile_aware_creator_angles: list[str] = Field(
        default_factory=list,
        description="Suggested angles tailored to the channel profile",
    )
    omission_patterns_by_side: dict[str, list[str]] = Field(
        default_factory=dict,
        description="What each side omits (key=bias_group, value=omitted topics)",
    )
    headline_framing_diffs: list[str] = Field(
        default_factory=list,
        description="Notable differences in how outlets headline the same story",
    )
    opinion_clusters: list[OpinionCluster] = Field(
        default_factory=list,
        description="Grouped opinions by ideological alignment",
    )
    evidence_confidence: str = Field(
        default="moderate",
        description="Overall confidence in narrative analysis: high, moderate, low",
    )
    missing_perspectives: list[str] = Field(
        default_factory=list,
        description="Ideological perspectives not represented in the source set",
    )
