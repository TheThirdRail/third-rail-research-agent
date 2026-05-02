import sys
import types
from pathlib import Path

from src.schemas.visual_evidence import MediaPointer, ResolvedSocialPost
from src.services.screenshot_capture_service import ScreenshotCaptureService
from src.services.social_post_resolver_service import SocialPostResolverService
from src.services.visual_evidence_service import VisualEvidenceService
from src.tools.article_extractor import ArticleExtractor


def test_article_extractor_captures_media_metadata():
    html = """
    <html>
      <head><meta property="og:image" content="https://example.com/card.jpg"></head>
      <body>
        <a href="https://x.com/example/status/123">post</a>
        <figure>
          <img src="https://example.com/inline.jpg" alt="Shells arranged as 8647">
          <figcaption>Photo shows seashells spelling 8647.</figcaption>
        </figure>
        <p>Body text about the story.</p>
      </body>
    </html>
    """
    article = ArticleExtractor()._extract_from_html(
        url="https://example.com/story",
        html_content=html,
        method="test",
    )

    assert article.og_image_url == "https://example.com/card.jpg"
    assert "https://x.com/example/status/123" in article.embedded_post_urls
    assert "Shells arranged as 8647" in article.image_alt_text
    assert "Photo shows seashells spelling 8647." in article.media_captions


def test_visual_evidence_uses_router_output(monkeypatch):
    class FakeRouter:
        def complete(self, messages, temperature=None, max_tokens=None):
            return """
            {
              "observable_text": "8647",
              "visible_symbols_or_numbers": ["8647"],
              "observable_objects": ["seashells"],
              "platform": "x",
              "confidence": 0.91
            }
            """

    monkeypatch.setattr(
        "src.services.visual_evidence_service.get_llm_router",
        lambda agent_name=None: FakeRouter(),
    )

    bundle = VisualEvidenceService().analyze(
        [
            MediaPointer(
                source_url="https://example.com/story",
                media_url="https://example.com/card.jpg",
                alt_text="Shells arranged as 8647",
            )
        ]
    )

    assert bundle.records[0].observable_text == "8647"
    assert bundle.records[0].visible_symbols_or_numbers == ["8647"]
    assert bundle.records[0].interpretation == ""
    assert bundle.records[0].legal_characterization == ""


def test_visual_evidence_falls_back_to_metadata_on_model_failure(monkeypatch):
    class FailingRouter:
        def complete(self, messages, temperature=None, max_tokens=None):
            raise RuntimeError("no vision model")

    monkeypatch.setattr(
        "src.services.visual_evidence_service.get_llm_router",
        lambda agent_name=None: FailingRouter(),
    )

    bundle = VisualEvidenceService().analyze(
        [
            MediaPointer(
                source_url="https://example.com/story",
                media_url="https://example.com/card.jpg",
                alt_text="Shells arranged as 8647",
            )
        ]
    )

    assert bundle.limitations
    assert bundle.records[0].observable_text == "Shells arranged as 8647"
    assert bundle.records[0].visible_symbols_or_numbers == ["8647"]


def test_social_post_resolver_canonicalizes_supported_platforms():
    resolver = SocialPostResolverService()

    assert (
        resolver.canonicalize("https://twitter.com/example/status/123?utm_source=x")
        == "https://x.com/example/status/123"
    )
    assert (
        resolver.canonicalize("https://www.instagram.com/p/ABC/?igshid=tracking")
        == "https://instagram.com/p/ABC"
    )
    assert resolver.platform_from_url("https://threads.net/@acct/post/1") == "threads"
    assert resolver.platform_from_url("https://facebook.com/story.php?id=1") == (
        "facebook"
    )
    assert resolver.platform_from_url("https://www.tiktok.com/@acct/video/1") == (
        "tiktok"
    )
    assert resolver.platform_from_url("https://truthsocial.com/@acct/posts/1") == (
        "truthsocial"
    )


def test_screenshot_capture_returns_structured_no_raw_artifact_fallback():
    artifact = ScreenshotCaptureService().capture(
        "https://x.com/example/status/123",
        source_url="https://example.com/story",
        platform="x",
    )

    assert not artifact.success
    assert artifact.artifact_path == ""
    assert artifact.fallback_reason == "browser_capture_unavailable"
    assert artifact.provenance["retention"] == "no_raw_screenshot_stored"


def test_screenshot_capture_saves_playwright_artifact(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    class FakeResponse:
        status = 200

    class FakePage:
        def goto(self, url, wait_until=None, timeout=None):
            captured["url"] = url
            captured["wait_until"] = wait_until
            captured["timeout"] = timeout
            return FakeResponse()

        def screenshot(self, path=None, full_page=None):
            captured["full_page"] = full_page
            Path(path).write_bytes(b"fake-png")

    class FakeBrowser:
        def new_page(self, viewport=None):
            captured["viewport"] = viewport
            return FakePage()

        def close(self):
            captured["closed"] = True

    class FakeChromium:
        def launch(self, args=None):
            captured["launch_args"] = args
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

    artifact = ScreenshotCaptureService(
        enabled=True,
        artifact_dir=tmp_path,
        timeout_ms=1234,
        viewport_width=800,
        viewport_height=600,
    ).capture(
        "https://x.com/example/status/123",
        source_url="https://example.com/story",
        platform="x",
    )

    assert artifact.success
    assert artifact.render_method == "playwright_sync"
    assert artifact.fallback_reason == ""
    assert Path(artifact.artifact_path).read_bytes() == b"fake-png"
    assert artifact.provenance["retention"] == "raw_screenshot_stored"
    assert artifact.provenance["ocr_status"] == "disabled"
    assert artifact.provenance["http_status"] == "200"
    assert captured["viewport"] == {"width": 800, "height": 600}
    assert captured["timeout"] == 1234
    assert captured["full_page"] is True
    assert captured["closed"] is True


def test_screenshot_capture_extracts_ocr_when_enabled(monkeypatch, tmp_path):
    class FakeResponse:
        status = 200

    class FakePage:
        def goto(self, url, wait_until=None, timeout=None):
            return FakeResponse()

        def screenshot(self, path=None, full_page=None):
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
    fake_pytesseract = types.SimpleNamespace(
        image_to_string=lambda path: "Visible OCR text 8647"
    )
    monkeypatch.setitem(sys.modules, "playwright", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_sync_api)
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)
    monkeypatch.setattr(
        ScreenshotCaptureService,
        "_blocked_target_reason",
        staticmethod(lambda target_url: ""),
    )

    artifact = ScreenshotCaptureService(
        enabled=True,
        ocr_enabled=True,
        artifact_dir=tmp_path,
    ).capture(
        "https://x.com/example/status/123",
        source_url="https://example.com/story",
        platform="x",
    )

    assert artifact.success
    assert artifact.ocr_text == "Visible OCR text 8647"
    assert artifact.provenance["ocr_status"] == "captured"


def test_screenshot_capture_blocks_private_targets_when_enabled():
    artifact = ScreenshotCaptureService(enabled=True).capture(
        "http://127.0.0.1:8000/private",
        source_url="https://example.com/story",
        platform="x",
    )

    assert not artifact.success
    assert artifact.render_method == "restricted_url_guard"
    assert artifact.fallback_reason == "blocked_private_or_local_url"
    assert artifact.artifact_path == ""
    assert artifact.provenance["retention"] == "no_raw_screenshot_stored"


def test_visual_evidence_routes_social_post_through_resolver():
    class FakeResolver:
        def resolve(self, post_url: str, *, source_url: str = ""):
            return ResolvedSocialPost(
                source_url=source_url,
                original_url=post_url,
                resolved_url="https://x.com/example/status/123",
                platform="x",
                metadata_text="Post text says 8647 with seashell image",
                fallback_reason="oembed_unavailable_for_platform",
            )

    bundle = VisualEvidenceService(social_resolver=FakeResolver()).analyze(
        [
            MediaPointer(
                source_url="https://example.com/story",
                media_url="https://twitter.com/example/status/123?utm_source=x",
                media_type="social_post",
                alt_text="Embedded X post",
            )
        ]
    )

    record = bundle.records[0]
    assert record.media_type == "social_post"
    assert record.platform == "x"
    assert record.resolved_url == "https://x.com/example/status/123"
    assert record.fallback_reason == "browser_capture_unavailable"
    assert "8647" in record.visible_symbols_or_numbers
    assert record.screenshot_provenance["retention"] == "no_raw_screenshot_stored"
