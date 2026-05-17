"""Structured report section schemas.

The analysis crew returns these fields as JSON. The deterministic renderer owns
all Markdown headings, source matrices, and citation blocks.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SourceFinding(BaseModel):
    """Per-source finding used to populate the deterministic Source Matrix."""

    source_id: str = ""
    key_framing: str = ""
    notable_claim: str = ""
    evidence_snippet: str = ""
    confidence: float = 0.0


class AnalysisReportSections(BaseModel):
    """Typed section payload produced by the analysis crew."""

    executive_summary: str = ""
    what_happened: str = ""
    directly_observable: str = ""
    what_is_disputed: str = ""
    coverage_snapshot: str = ""
    agreed_facts: str = ""
    opinion_analysis: str = ""
    framing_omissions: str = ""
    logical_fallacies: str = ""
    linguistic_manipulation: str = ""
    fact_opinion_ambiguities: str = ""
    mainstream_narrative: str = ""
    alternative_takes: str = ""
    creator_angles: list[str] = Field(default_factory=list)
    recommended_approach: str = ""
    video_outline: str = ""
    evidence_limitations: list[str] = Field(default_factory=list)
    source_findings: list[SourceFinding] = Field(default_factory=list)

    @field_validator("*", mode="before")
    @classmethod
    def _normalize_strings(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @classmethod
    def from_crew_payload(
        cls,
        payload: dict[str, Any],
        *,
        fallback_summary: str = "",
    ) -> AnalysisReportSections:
        """Parse the structured section payload returned by ``run_analysis``.

        Backward compatibility is intentionally narrow: a plain ``report`` value
        can become a summary only when it is not already a Markdown report.
        """
        if isinstance(payload.get("sections"), dict):
            return cls.model_validate(payload["sections"])

        raw = payload.get("report_json") or payload.get("report") or ""
        if isinstance(raw, dict):
            return cls.model_validate(raw)

        parsed = _parse_json_object(str(raw))
        if parsed:
            return cls.model_validate(parsed)

        if raw and _contains_markdown_heading(str(raw)):
            raise ValueError(
                "Crew analysis returned Markdown instead of structured report JSON."
            )

        return cls(executive_summary=str(raw or fallback_summary).strip())

    def to_renderer_sections(self):
        """Convert to the dataclass used by the deterministic renderer."""
        from src.services.report_renderer import ReportSections

        return ReportSections(
            executive_summary=self.executive_summary,
            what_happened=self.what_happened,
            directly_observable=self.directly_observable,
            what_is_disputed=self.what_is_disputed,
            coverage_snapshot=self.coverage_snapshot,
            agreed_facts=self.agreed_facts,
            opinion_analysis=self.opinion_analysis,
            framing_omissions=self.framing_omissions,
            logical_fallacies=self.logical_fallacies,
            linguistic_manipulation=self.linguistic_manipulation,
            fact_opinion_ambiguities=self.fact_opinion_ambiguities,
            mainstream_narrative=self.mainstream_narrative,
            alternative_takes=self.alternative_takes,
            creator_angles=self.creator_angles,
            recommended_approach=self.recommended_approach,
            video_outline=self.video_outline,
            evidence_limitations=self.evidence_limitations,
        )


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    elif not text.startswith("{"):
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if not match:
            return None
        text = match.group(1)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _contains_markdown_heading(raw: str) -> bool:
    return bool(re.search(r"(?im)^#{1,6}\s+\S+", raw))
