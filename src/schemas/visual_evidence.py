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
    resolved_url: str = ""
    media_type: str = "image"
    platform: str = ""
    render_method: str = ""
    screenshot_artifact_path: str = ""
    screenshot_provenance: dict[str, str] = Field(default_factory=dict)
    ocr_text: str = ""
    fallback_reason: str = ""
    observable_text: str = ""
    visible_symbols_or_numbers: list[str] = Field(default_factory=list)
    observable_objects: list[str] = Field(default_factory=list)
    reported_context: str = ""
    interpretation: str = ""
    legal_characterization: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ResolvedSocialPost(BaseModel):
    """Canonical social-post metadata resolved without interpretation."""

    source_url: str
    original_url: str
    resolved_url: str
    platform: str
    metadata_text: str = ""
    author_name: str = ""
    provider_name: str = ""
    oembed_html: str = ""
    resolution_method: str = "canonical_url"
    success: bool = True
    fallback_reason: str = ""


class ScreenshotArtifact(BaseModel):
    """Screenshot capture provenance without storing raw screenshot bytes."""

    source_url: str
    target_url: str
    platform: str = ""
    render_method: str = ""
    artifact_path: str = ""
    ocr_text: str = ""
    success: bool = False
    fallback_reason: str = ""
    provenance: dict[str, str] = Field(default_factory=dict)


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
                    f"Resolved URL: {record.resolved_url or record.media_url}",
                    f"Platform: {record.platform or 'unknown'}",
                    f"Render method: {record.render_method or 'not captured'}",
                    f"OCR text: {record.ocr_text or 'none captured'}",
                    f"Fallback reason: {record.fallback_reason or 'none'}",
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
