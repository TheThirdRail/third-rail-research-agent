"""Pydantic schemas for structured fact extraction."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ClaimType(str, Enum):
    """Types of claims that can be extracted from sources."""

    OBSERVED_FACT = "observed_fact"
    ATTRIBUTED_STATEMENT = "attributed_statement"
    ALLEGATION = "allegation"
    CAUSAL_INFERENCE = "causal_inference"
    PREDICTION = "prediction"
    OPINION = "opinion"


class CoverageStatus(str, Enum):
    """How a claim is covered across the ideological spectrum."""

    CROSS_SOURCED = "cross_sourced"
    SIDE_SPECIFIC = "side_specific"
    DISPUTED = "disputed"
    ASYMMETRICALLY_COVERED = "asymmetrically_covered"


class Claim(BaseModel):
    """A single structured claim extracted from source material."""

    claim_id: str = Field(description="Unique identifier for this claim")
    normalized_claim: str = Field(description="Canonicalized claim statement")
    claim_type: ClaimType = Field(description="Type of claim")
    entities: list[str] = Field(
        default_factory=list,
        description="Named entities referenced in the claim",
    )
    time_scope: str = Field(
        default="",
        description="When this claim applies or occurred",
    )
    source_ids: list[str] = Field(
        default_factory=list,
        description="IDs of sources that support this claim",
    )
    bias_buckets_present: list[str] = Field(
        default_factory=list,
        description="Bias bucket labels of sources reporting this claim",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence in the claim's accuracy (0.0-1.0)",
    )
    evidence_strength: str = Field(
        default="moderate",
        description="Strength of evidence: strong, moderate, weak, unverified",
    )
    coverage_status: CoverageStatus = Field(
        default=CoverageStatus.SIDE_SPECIFIC,
        description="How this claim is covered across ideological spectrum",
    )


class CoverageAsymmetry(BaseModel):
    """Analysis of what different sides emphasize or omit."""

    right_emphasizes: list[str] = Field(
        default_factory=list,
        description="Claims or facts emphasized by right-leaning sources",
    )
    left_emphasizes: list[str] = Field(
        default_factory=list,
        description="Claims or facts emphasized by left-leaning sources",
    )
    center_ignores: list[str] = Field(
        default_factory=list,
        description="Claims or facts notably absent from center sources",
    )
    fringe_adds: list[str] = Field(
        default_factory=list,
        description="Claims uniquely present in fringe/conspiracy sources",
    )
    likely_framing_implication: str = Field(
        default="",
        description="What the asymmetry pattern suggests about framing",
    )


class FactExtractionResult(BaseModel):
    """Complete output from the structured fact extraction stage."""

    claims: list[Claim] = Field(
        default_factory=list,
        description="All extracted and classified claims",
    )
    coverage_asymmetry: CoverageAsymmetry = Field(
        default_factory=CoverageAsymmetry,
        description="Analysis of coverage asymmetry across ideological lines",
    )
    agreed_facts_summary: str = Field(
        default="",
        description="Brief summary of facts agreed upon across sources",
    )
    disputed_facts_summary: str = Field(
        default="",
        description="Brief summary of facts disputed between sources",
    )
