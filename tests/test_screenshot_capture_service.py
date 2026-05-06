"""Focused screenshot/OCR fallback tests with mocked browser and OCR paths."""

import builtins
import sys
import types
from pathlib import Path

from src.services.screenshot_capture_service import ScreenshotCaptureService


def _install_fake_playwright(monkeypatch, *, screenshot_error: Exception | None = None):
    class FakeResponse:
        status = 200

    class FakePage:
        def goto(self, url, wait_until=None, timeout=None):
            return FakeResponse()

        def screenshot(self, path=None, full_page=None):
            if screenshot_error:
                raise screenshot_error
            Path(path).write_bytes(b"fake-png")

    class FakeBrowser:
        def new_page(self, viewport=None):
            return FakePage()

        def close(self):
            pass

    class FakeChromium:
        def launch(self, args=None):
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakeContext:
        def __enter__(self):
            return FakePlaywright()

        def __exit__(self, exc_type, exc, traceback):
            return False

    fake_sync_api = types.SimpleNamespace(
        TimeoutError=TimeoutError,
        sync_playwright=lambda: FakeContext(),
    )
    monkeypatch.setitem(sys.modules, "playwright", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_sync_api)
    monkeypatch.setattr(
        ScreenshotCaptureService,
        "_blocked_target_reason",
        staticmethod(lambda target_url: ""),
    )


def test_disabled_capture_returns_predictable_fallback():
    artifact = ScreenshotCaptureService(enabled=False).capture(
        "https://x.com/example/status/123"
    )

    assert not artifact.success
    assert artifact.fallback_reason == "browser_capture_unavailable"
    assert artifact.provenance["ocr_status"] == "not_attempted"


def test_private_local_url_is_blocked_when_capture_enabled():
    artifact = ScreenshotCaptureService(enabled=True).capture(
        "http://127.0.0.1:8000/private"
    )

    assert not artifact.success
    assert artifact.render_method == "restricted_url_guard"
    assert artifact.fallback_reason == "blocked_private_or_local_url"


def test_playwright_import_failure_returns_structured_fallback(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "playwright.sync_api":
            raise ImportError("missing playwright")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(
        ScreenshotCaptureService,
        "_blocked_target_reason",
        staticmethod(lambda target_url: ""),
    )

    artifact = ScreenshotCaptureService(enabled=True).capture("https://example.com")

    assert not artifact.success
    assert artifact.fallback_reason.startswith("playwright_unavailable:")


def test_playwright_runtime_failure_returns_structured_fallback(monkeypatch, tmp_path):
    _install_fake_playwright(monkeypatch, screenshot_error=RuntimeError("boom"))

    artifact = ScreenshotCaptureService(
        enabled=True,
        artifact_dir=tmp_path,
    ).capture("https://example.com")

    assert not artifact.success
    assert artifact.fallback_reason == "browser_capture_failed: boom"


def test_ocr_disabled_leaves_text_empty(monkeypatch, tmp_path):
    _install_fake_playwright(monkeypatch)

    artifact = ScreenshotCaptureService(
        enabled=True,
        ocr_enabled=False,
        artifact_dir=tmp_path,
    ).capture("https://example.com")

    assert artifact.success
    assert artifact.ocr_text == ""
    assert artifact.provenance["ocr_status"] == "disabled"


def test_ocr_import_failure_records_limitation(monkeypatch, tmp_path):
    _install_fake_playwright(monkeypatch)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pytesseract":
            raise ImportError("missing pytesseract")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    artifact = ScreenshotCaptureService(
        enabled=True,
        ocr_enabled=True,
        artifact_dir=tmp_path,
    ).capture("https://example.com")

    assert artifact.success
    assert artifact.ocr_text == ""
    assert artifact.provenance["ocr_status"] == "unavailable"
    assert "pytesseract_unavailable" in artifact.provenance["ocr_error"]


def test_ocr_runtime_failure_records_limitation(monkeypatch, tmp_path):
    _install_fake_playwright(monkeypatch)
    fake_pytesseract = types.SimpleNamespace(
        image_to_string=lambda path: (_ for _ in ()).throw(RuntimeError("ocr boom"))
    )
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)

    artifact = ScreenshotCaptureService(
        enabled=True,
        ocr_enabled=True,
        artifact_dir=tmp_path,
    ).capture("https://example.com")

    assert artifact.success
    assert artifact.ocr_text == ""
    assert artifact.provenance["ocr_status"] == "failed"
    assert artifact.provenance["ocr_error"] == "ocr_failed: ocr boom"


def test_successful_screenshot_writes_to_tmp_path(monkeypatch, tmp_path):
    _install_fake_playwright(monkeypatch)

    artifact = ScreenshotCaptureService(
        enabled=True,
        artifact_dir=tmp_path,
    ).capture("https://example.com")

    assert artifact.success
    assert Path(artifact.artifact_path).is_relative_to(tmp_path)
    assert Path(artifact.artifact_path).read_bytes() == b"fake-png"
