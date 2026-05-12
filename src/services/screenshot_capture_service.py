"""Restricted screenshot capture facade for social/visual evidence."""

from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from src.core.config import settings
from src.schemas.visual_evidence import ScreenshotArtifact
from src.utils.url_utils import blocked_public_url_reason


class ScreenshotCaptureService:
    """Capture public web screenshots with a fail-open structured fallback."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        artifact_dir: Path | None = None,
        timeout_ms: int | None = None,
        viewport_width: int | None = None,
        viewport_height: int | None = None,
        ocr_enabled: bool | None = None,
    ) -> None:
        self.enabled = (
            settings.screenshot_capture_enabled if enabled is None else enabled
        )
        self.ocr_enabled = (
            settings.screenshot_ocr_enabled if ocr_enabled is None else ocr_enabled
        )
        self.artifact_dir = artifact_dir or (
            settings.data_dir / "artifacts" / "screenshots"
        )
        self.timeout_ms = timeout_ms or settings.screenshot_capture_timeout_ms
        self.viewport_width = (
            viewport_width or settings.screenshot_capture_viewport_width
        )
        self.viewport_height = (
            viewport_height or settings.screenshot_capture_viewport_height
        )

    def capture(
        self,
        target_url: str,
        *,
        source_url: str = "",
        platform: str = "",
    ) -> ScreenshotArtifact:
        """Capture a screenshot artifact or return a structured fallback."""
        captured_at = datetime.now(UTC).isoformat()
        base_provenance = {
            "captured_at": captured_at,
            "retention": "no_raw_screenshot_stored",
        }

        if not self.enabled:
            return self._fallback(
                target_url,
                source_url=source_url,
                platform=platform,
                render_method="not_configured",
                fallback_reason="browser_capture_unavailable",
                provenance={**base_provenance, "ocr_status": "not_attempted"},
            )

        blocked_reason = self._blocked_target_reason(target_url)
        if blocked_reason:
            return self._fallback(
                target_url,
                source_url=source_url,
                platform=platform,
                render_method="restricted_url_guard",
                fallback_reason=blocked_reason,
                provenance={**base_provenance, "ocr_status": "not_attempted"},
            )

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            return self._fallback(
                target_url,
                source_url=source_url,
                platform=platform,
                render_method="playwright_sync",
                fallback_reason="browser_capture_unavailable_in_event_loop",
                provenance={**base_provenance, "ocr_status": "not_attempted"},
            )

        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            return self._fallback(
                target_url,
                source_url=source_url,
                platform=platform,
                render_method="playwright_sync",
                fallback_reason=f"playwright_unavailable: {exc}",
                provenance={**base_provenance, "ocr_status": "not_attempted"},
            )

        artifact_path = self._artifact_path(target_url, platform)
        try:
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(args=["--no-sandbox"])
                try:
                    page = browser.new_page(
                        viewport={
                            "width": self.viewport_width,
                            "height": self.viewport_height,
                        }
                    )
                    if hasattr(page, "route"):
                        page.route("**/*", self._guarded_playwright_route)
                    response = page.goto(
                        target_url,
                        wait_until="networkidle",
                        timeout=self.timeout_ms,
                    )
                    status = response.status if response is not None else None
                    page.screenshot(path=str(artifact_path), full_page=True)
                finally:
                    browser.close()
        except PlaywrightTimeoutError:
            return self._fallback(
                target_url,
                source_url=source_url,
                platform=platform,
                render_method="playwright_sync",
                fallback_reason="browser_capture_timeout",
                provenance={**base_provenance, "ocr_status": "not_attempted"},
            )
        except Exception as exc:
            return self._fallback(
                target_url,
                source_url=source_url,
                platform=platform,
                render_method="playwright_sync",
                fallback_reason=f"browser_capture_failed: {exc}",
                provenance={**base_provenance, "ocr_status": "not_attempted"},
            )

        ocr_text, ocr_provenance = self._extract_ocr_text(artifact_path)
        provenance = {
            **base_provenance,
            "retention": "raw_screenshot_stored",
            "viewport": f"{self.viewport_width}x{self.viewport_height}",
            "http_status": str(status) if status is not None else "",
            **ocr_provenance,
        }
        return ScreenshotArtifact(
            source_url=source_url,
            target_url=target_url,
            platform=platform,
            render_method="playwright_sync",
            artifact_path=str(artifact_path),
            ocr_text=ocr_text,
            success=True,
            fallback_reason="",
            provenance=provenance,
        )

    def _extract_ocr_text(self, artifact_path: Path) -> tuple[str, dict[str, str]]:
        if not self.ocr_enabled:
            return "", {"ocr_status": "disabled"}
        try:
            import pytesseract  # type: ignore[import-not-found]
        except Exception as exc:
            return "", {
                "ocr_status": "unavailable",
                "ocr_error": f"pytesseract_unavailable: {exc}",
            }
        try:
            text = str(pytesseract.image_to_string(str(artifact_path))).strip()
        except Exception as exc:
            return "", {
                "ocr_status": "failed",
                "ocr_error": f"ocr_failed: {exc}",
            }
        return text, {"ocr_status": "captured" if text else "empty"}

    @staticmethod
    def _fallback(
        target_url: str,
        *,
        source_url: str,
        platform: str,
        render_method: str,
        fallback_reason: str,
        provenance: dict[str, str],
    ) -> ScreenshotArtifact:
        return ScreenshotArtifact(
            source_url=source_url,
            target_url=target_url,
            platform=platform,
            render_method=render_method,
            success=False,
            fallback_reason=fallback_reason,
            provenance=provenance,
        )

    @staticmethod
    def _blocked_target_reason(target_url: str) -> str:
        return blocked_public_url_reason(target_url)

    @staticmethod
    def _guarded_playwright_route(route) -> None:
        reason = blocked_public_url_reason(route.request.url)
        if reason:
            route.abort()
            return
        route.continue_()

    def _artifact_path(self, target_url: str, platform: str) -> Path:
        parsed = urlparse(target_url)
        host = re.sub(r"[^A-Za-z0-9_.-]+", "_", parsed.hostname or "unknown")
        label = re.sub(r"[^A-Za-z0-9_.-]+", "_", platform or host).strip("_")
        digest = hashlib.sha256(target_url.encode("utf-8")).hexdigest()[:16]
        return self.artifact_dir / (label or "capture") / f"{digest}.png"
