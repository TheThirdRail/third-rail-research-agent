from types import SimpleNamespace

import pytest

from src.tools.article_extractor import ArticleExtractor, ExtractedArticle


class _RedirectResponse:
    is_redirect = True
    status_code = 302
    headers = {"location": "http://127.0.0.1/private"}
    text = ""
    url = "https://example.com/start"

    def raise_for_status(self):
        raise AssertionError("redirect responses should not be raised")


class _RedirectClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def get(self, url: str):
        assert url == "https://example.com/start"
        return _RedirectResponse()


class _HtmlResponse:
    is_redirect = False
    status_code = 200
    text = "<html><title>Safe</title><p>story body</p></html>"
    url = "https://example.com/start"

    def raise_for_status(self):
        pass


class _HtmlClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def get(self, url: str):
        assert url == "https://example.com/start"
        return _HtmlResponse()


def test_extract_blocks_loopback_before_extractor_attempts(monkeypatch):
    extractor = ArticleExtractor()
    monkeypatch.setattr(
        extractor,
        "extract_trafilatura",
        lambda url: pytest.fail("unsafe URL reached trafilatura"),
    )

    result = extractor.extract("http://127.0.0.1:8000/internal")

    assert result.success is False
    assert result.error_code == "unsafe_url"
    assert result.error == "blocked_private_or_local_url"
    assert result.extractor_method == "url_validation"


@pytest.mark.asyncio
async def test_extract_async_blocks_localhost_before_extractor_attempts(monkeypatch):
    extractor = ArticleExtractor()

    async def fail_extract(url: str):
        pytest.fail("unsafe URL reached async trafilatura")

    monkeypatch.setattr(extractor, "extract_trafilatura_async", fail_extract)

    result = await extractor.extract_async("http://localhost:8000/internal")

    assert result.success is False
    assert result.error_code == "unsafe_url"
    assert result.error == "blocked_private_or_local_url"
    assert result.extractor_method == "url_validation"


def test_trafilatura_prefetch_blocks_redirect_to_private_url(monkeypatch):
    extractor = ArticleExtractor()
    monkeypatch.setattr(
        "src.utils.url_utils.socket.getaddrinfo",
        lambda *args, **kwargs: [
            (0, 0, 0, "", ("93.184.216.34", 443)),
        ],
    )
    monkeypatch.setattr(
        "src.tools.article_extractor.httpx.Client",
        lambda **kwargs: _RedirectClient(),
    )

    result = extractor.extract_trafilatura("https://example.com/start")

    assert result.success is False
    assert result.error_code == "unsafe_url"
    assert result.error == "blocked_private_or_local_url"


def test_trafilatura_uses_prefetched_html_without_fetch_url(monkeypatch):
    extractor = ArticleExtractor()
    monkeypatch.setattr(
        "src.utils.url_utils.socket.getaddrinfo",
        lambda *args, **kwargs: [
            (0, 0, 0, "", ("93.184.216.34", 443)),
        ],
    )
    monkeypatch.setattr(
        "src.tools.article_extractor.httpx.Client",
        lambda **kwargs: _HtmlClient(),
    )

    import trafilatura

    monkeypatch.setattr(
        trafilatura,
        "fetch_url",
        lambda url: pytest.fail("trafilatura.fetch_url must not run"),
    )
    monkeypatch.setattr(
        trafilatura,
        "extract",
        lambda html, **kwargs: "Safe article body " * 20,
    )
    monkeypatch.setattr(
        trafilatura,
        "extract_metadata",
        lambda html: SimpleNamespace(title="Safe", author=None, date=None),
    )

    result = extractor.extract_trafilatura("https://example.com/start")

    assert result.success is True
    assert result.extractor_method == "trafilatura"
    assert result.http_status == 200


def test_automatic_extraction_skips_selenium_before_firecrawl(monkeypatch):
    extractor = ArticleExtractor()
    monkeypatch.setattr(
        "src.utils.url_utils.socket.getaddrinfo",
        lambda *args, **kwargs: [
            (0, 0, 0, "", ("93.184.216.34", 443)),
        ],
    )

    def failed(method: str):
        return ExtractedArticle(
            title="",
            text="",
            author=None,
            date=None,
            domain="example.com",
            url="https://example.com/story",
            success=False,
            error="failed",
            error_code="exception",
            extractor_method=method,
        )

    monkeypatch.setattr(extractor, "extract_trafilatura", lambda url: failed("t"))
    monkeypatch.setattr(extractor, "extract_newspaper", lambda url: failed("n"))
    monkeypatch.setattr(extractor, "extract_fundus", lambda url: failed("f"))
    monkeypatch.setattr(extractor, "extract_playwright", lambda url: failed("p"))
    monkeypatch.setattr(
        extractor,
        "extract_selenium",
        lambda url: pytest.fail("selenium should not run automatically"),
    )
    monkeypatch.setattr(
        "src.tools.article_extractor.settings.enable_selenium_fallback",
        True,
    )
    monkeypatch.setattr(
        extractor,
        "extract_firecrawl",
        lambda url: failed("firecrawl"),
    )

    result = extractor.extract("https://example.com/story")

    assert result.success is False
    assert result.extractor_method == "firecrawl"
