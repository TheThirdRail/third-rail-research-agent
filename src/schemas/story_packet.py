"""Pydantic schemas for story parsing output."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class StoryPacket(BaseModel):
    """Structured output from story parsing.

    Provides canonical headline, entities, search terms, and disambiguation
    metadata for downstream services (relevance scorer, source planner,
    source aggregator).
    """

    canonical_headline: str = Field(
        description="Normalized headline summarizing the story"
    )
    actors: list[str] = Field(
        default_factory=list,
        description="Key people/organizations involved",
    )
    action_verbs: list[str] = Field(
        default_factory=list,
        description="Primary actions/events (e.g., 'vetoed', 'arrested', 'proposed')",
    )
    location: str = Field(
        default="",
        description="Primary geographic location if relevant",
    )
    time_window_start: datetime | None = Field(
        default=None,
        description="Estimated event start date",
    )
    time_window_end: datetime | None = Field(
        default=None,
        description="Estimated event end date",
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="Alternative names, abbreviations, or spellings for key entities",
    )
    distinctive_terms: list[str] = Field(
        default_factory=list,
        description="Distinctive codes, quoted numbers, platforms, or visual terms",
    )
    visual_descriptors: list[str] = Field(
        default_factory=list,
        description="Visual descriptors that materially identify the story",
    )
    must_have_terms: list[str] = Field(
        default_factory=list,
        description="Terms that MUST appear in a relevant article",
    )
    must_not_have_terms: list[str] = Field(
        default_factory=list,
        description="Terms that indicate a DIFFERENT story (for disambiguation)",
    )
    query_pack: list[str] = Field(
        default_factory=list,
        description="Pre-built search queries for source finding",
    )
    disambiguation_notes: str = Field(
        default="",
        description="Notes on how to distinguish this story from similar ones",
    )
