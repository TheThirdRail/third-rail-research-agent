"""Schemas for visual and social-post observable evidence."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MediaPointer(BaseModel):
    """A pointer to media discovered during extraction."""

    source_url: str
    media_url: str
    media_type: str = "image"
    platform: str = ""
    alt_text: str = ""
    caption: str = ""


class VisualEvidenceRecord(BaseModel):
    """Structured observation separated from interpretation."""

    source_url: str
    media_url: str
    media_type: str = "image"
    platform: str = ""
    observable_text: str = ""
    visible_symbols_or_numbers: list[str] = Field(default_factory=list)
    observable_objects: list[str] = Field(default_factory=list)
    reported_context: str = ""
    interpretation: str = ""
    legal_characterization: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class VisualEvidenceBundle(BaseModel):
    """Visual evidence records plus non-fatal limitations."""

    records: list[VisualEvidenceRecord] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    def to_context_block(self) -> str:
        """Format records for CrewAI context."""
        if not self.records and not self.limitations:
            return ""
        lines: list[str] = []
        for index, record in enumerate(self.records, 1):
            lines.extend(
                [
                    f"Visual Evidence V{index}:",
                    f"Source URL: {record.source_url}",
                    f"Media URL: {record.media_url}",
                    f"Platform: {record.platform or 'unknown'}",
                    f"Observable text: {record.observable_text or 'none observed'}",
                    "Visible symbols/numbers: "
                    + (", ".join(record.visible_symbols_or_numbers) or "none observed"),
                    "Observable objects: "
                    + (", ".join(record.observable_objects) or "none observed"),
                    f"Confidence: {record.confidence:.2f}",
                    "Interpretation/legal characterization: not inferred here",
                    "",
                ]
            )
        for limitation in self.limitations:
            lines.append(f"Limitation: {limitation}")
        return "\n".join(lines).strip()
