"""Deterministic report renderer.

Builds Source Matrix, footnotes, evidence-limit banners, and
section structure from persisted source records and structured
analysis output — eliminating model-generated formatting drift.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SourceRecord:
    """A source record for report rendering."""
    source_id: str
    title: str
    domain: str
    url: str
    bias: int
    bias_label: str
    confidence: float
    key_framing: str = ""


@dataclass
class ReportSections:
    """Structured sections from the analysis crew."""
    executive_summary: str = ""
    story_overview: str = ""
    agreed_facts: str = ""
    disputed_facts: str = ""
    opinion_analysis: str = ""
    framing_omissions: str = ""
    logical_fallacies: str = ""
    linguistic_manipulation: str = ""
    fact_opinion_ambiguities: str = ""
    mainstream_narrative: str = ""
    alternative_takes: str = ""
    creator_angles: list[str] = field(default_factory=list)
    recommended_approach: str = ""
    video_outline: str = ""
    evidence_limitations: list[str] = field(default_factory=list)


class ReportRenderer:
    """Renders a final Markdown report from structured inputs."""

    def render(
        self,
        sources: list[SourceRecord],
        sections: ReportSections,
        missing_buckets: list[str] | None = None,
    ) -> str:
        """Render a complete Markdown report.

        Args:
            sources: List of source records for the Source Matrix.
            sections: Structured section content from analysis crew.
            missing_buckets: List of required but unfilled bias buckets.

        Returns:
            Complete Markdown report string.
        """
        parts: list[str] = []

        # Evidence Limitations Banner (top of report if applicable)
        if missing_buckets or sections.evidence_limitations:
            parts.append(self._render_evidence_limits(
                missing_buckets or [], sections.evidence_limitations
            ))

        # Executive Summary
        if sections.executive_summary:
            parts.append(f"## Executive Summary\n\n{sections.executive_summary}")

        # Story Overview
        if sections.story_overview:
            parts.append(f"## Story Overview\n\n{sections.story_overview}")

        # Source Matrix (deterministic)
        parts.append(self._render_source_matrix(sources))

        # Agreed Facts
        if sections.agreed_facts:
            parts.append(f"## Agreed Facts\n\n{sections.agreed_facts}")

        # Disputed Facts
        if sections.disputed_facts:
            parts.append(f"## Disputed Facts\n\n{sections.disputed_facts}")

        # Opinion Analysis
        if sections.opinion_analysis:
            parts.append(f"## Opinion Analysis\n\n{sections.opinion_analysis}")

        # Framing & Context Omissions
        if sections.framing_omissions:
            parts.append(f"## Framing & Context Omissions\n\n{sections.framing_omissions}")

        # Logical Fallacies
        if sections.logical_fallacies:
            parts.append(f"## Logical Fallacies\n\n{sections.logical_fallacies}")

        # Linguistic Manipulation & Dog Whistles
        if sections.linguistic_manipulation:
            parts.append(f"## Linguistic Manipulation & Dog Whistles\n\n{sections.linguistic_manipulation}")

        # Fact vs Opinion Ambiguities
        if sections.fact_opinion_ambiguities:
            parts.append(f"## Fact vs Opinion Ambiguities\n\n{sections.fact_opinion_ambiguities}")

        # Narrative Analysis — Evidence-Derived
        parts.append("## Evidence-Derived Narrative Patterns")
        if sections.mainstream_narrative:
            parts.append(f"### Mainstream Narrative\n\n{sections.mainstream_narrative}")
        if sections.alternative_takes:
            parts.append(f"### Alternative Takes\n\n{sections.alternative_takes}")

        # Narrative Analysis — Profile-Aware Creator Angles
        if sections.creator_angles:
            parts.append("## Profile-Aware Creator Angles\n")
            for angle in sections.creator_angles:
                parts.append(f"- {angle}")
            parts.append("")

        # Recommended Approach
        if sections.recommended_approach:
            parts.append(f"## Recommended Approach\n\n{sections.recommended_approach}")

        # Video Outline
        if sections.video_outline:
            parts.append(f"## Video Outline\n\n{sections.video_outline}")

        # Footnotes (deterministic)
        parts.append(self._render_footnotes(sources))

        return "\n\n".join(parts)

    def _render_evidence_limits(
        self, missing_buckets: list[str], limitations: list[str]
    ) -> str:
        """Render evidence limitations banner at the top."""
        lines = ["## ⚠️ Evidence Limitations\n"]
        if missing_buckets:
            bucket_list = ", ".join(missing_buckets)
            lines.append(
                f"**Missing ideological coverage:** {bucket_list}. "
                "The source set does not include perspectives from these "
                "bias groups. Conclusions may be incomplete.\n"
            )
        for limitation in limitations:
            lines.append(f"- {limitation}")
        return "\n".join(lines)

    def _render_source_matrix(self, sources: list[SourceRecord]) -> str:
        """Render deterministic Source Matrix table."""
        lines = [
            "## Source Matrix\n",
            "| # | Source | Domain | URL | Bias | Confidence | Key Framing / Claim |",
            "|---|--------|--------|-----|------|------------|---------------------|",
        ]
        for i, src in enumerate(sources, 1):
            source_link = f"[{src.title[:60]}]({src.url})"
            bias_display = f"{src.bias:+d} ({src.bias_label})"
            conf_display = f"{src.confidence:.0%}"
            framing = src.key_framing or "—"
            lines.append(
                f"| S{i} | {source_link} | {src.domain} | {src.url} | "
                f"{bias_display} | {conf_display} | {framing} |"
            )
        return "\n".join(lines)

    def _render_footnotes(self, sources: list[SourceRecord]) -> str:
        """Render deterministic footnote block."""
        lines = ["## All Sources & Citations\n"]
        for i, src in enumerate(sources, 1):
            lines.append(f"[^{i}]: {src.title} — {src.url}")
        return "\n".join(lines)
