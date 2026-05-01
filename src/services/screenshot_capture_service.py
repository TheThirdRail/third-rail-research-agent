"""Restricted screenshot capture façade for social/visual evidence."""

from __future__ import annotations

from datetime import UTC, datetime

from src.schemas.visual_evidence import ScreenshotArtifact


class ScreenshotCaptureService:
    """Record screenshot capture provenance without adding browser dependencies."""

    def capture(
        self,
        target_url: str,
        *,
        source_url: str = "",
        platform: str = "",
    ) -> ScreenshotArtifact:
        """Return a structured fallback until a restricted browser is configured."""
        return ScreenshotArtifact(
            source_url=source_url,
            target_url=target_url,
            platform=platform,
            render_method="not_configured",
            success=False,
            fallback_reason="browser_capture_unavailable",
            provenance={
                "captured_at": datetime.now(UTC).isoformat(),
                "retention": "no_raw_screenshot_stored",
            },
        )
