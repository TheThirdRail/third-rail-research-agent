import pytest

from src.tools.article_extractor import (
    ERROR_BLOCKED_CHALLENGE,
    ERROR_MISSING_API_KEY,
    ERROR_UNSAFE_URL,
    ArticleExtractor,
    ExtractedArticle,
)


def _success(url: str, method: str, text: str | None = None) -> ExtractedArticle:
    return ExtractedArticle(
        title=f"{method} title",
        text=text or (f"{method} extracted text. " * 20),
        author=None,
        date=None,
        domain="example.com",
        url=url,
        success=True,
        error=None,
        error_code=None,
        extractor_method=method,
    )


def _failure(extractor: ArticleExtractor, url: str, method: str) -> ExtractedArticle:
    return extractor._failure(
        url=url,
        error=f"{method} failed",
        error_code="empty_content",
        method=method,
    )


def test_crawl4ai_success_returns_immediately(monkeypatch):
    extractor = ArticleExtractor()
    monkeypatch.setattr(extractor, "_public_url_error", lambda url: None)
    calls = []

    def crawl4ai(url: str) -> ExtractedArticle:
        calls.append("crawl4ai")
        return _success(url, "crawl4ai")

    def fail_if_called(url: str) -> ExtractedArticle:
        raise AssertionError(f"unexpected fallback for {url}")

    monkeypatch.setattr(extractor, "extract_crawl4ai", crawl4ai)
    monkeypatch.setattr(extractor, "extract_trafilatura", fail_if_called)
    monkeypatch.setattr(extractor, "extract_firecrawl", fail_if_called)

    result = extractor.extract("https://example.com/story")

    assert result.success is True
    assert result.extractor_method == "crawl4ai"
    assert calls == ["crawl4ai"]


def test_crawl4ai_failure_falls_back_to_trafilatura(monkeypatch):
    extractor = ArticleExtractor()
    monkeypatch.setattr(extractor, "_public_url_error", lambda url: None)
    calls = []

    def crawl4ai(url: str) -> ExtractedArticle:
        calls.append("crawl4ai")
        return _failure(extractor, url, "crawl4ai")

    def trafilatura(url: str) -> ExtractedArticle:
        calls.append("trafilatura")
        return _success(url, "trafilatura")

    def fail_if_called(url: str) -> ExtractedArticle:
        raise AssertionError(f"unexpected firecrawl call for {url}")

    monkeypatch.setattr(extractor, "extract_crawl4ai", crawl4ai)
    monkeypatch.setattr(extractor, "extract_trafilatura", trafilatura)
    monkeypatch.setattr(extractor, "extract_firecrawl", fail_if_called)

    result = extractor.extract("https://example.com/story")

    assert result.success is True
    assert result.extractor_method == "trafilatura"
    assert calls == ["crawl4ai", "trafilatura"]


@pytest.mark.asyncio
async def test_crawl4ai_progressive_enhancement_escalates_on_block(monkeypatch):
    extractor = ArticleExtractor()
    monkeypatch.setattr(extractor, "_public_url_error", lambda url: None)
    monkeypatch.setattr(
        "src.tools.article_extractor.settings.crawl4ai_progressive_undetected_enabled",
        True,
    )
    monkeypatch.setattr(
        extractor,
        "_import_crawl4ai_core",
        lambda: (object(), object(), object(), object()),
    )
    calls = []

    async def run_attempt(url, attempt, **kwargs):
        calls.append((attempt.label, attempt.use_undetected, attempt.enable_stealth))
        if attempt.label == "undetected":
            return _success(url, "crawl4ai")
        return extractor._failure(
            url=url,
            error="blocked",
            error_code=ERROR_BLOCKED_CHALLENGE,
            method="crawl4ai",
        )

    monkeypatch.setattr(extractor, "_run_crawl4ai_attempt", run_attempt)

    result = await extractor.extract_crawl4ai_async("https://example.com/story")

    assert result.success is True
    assert result.extractor_method == "crawl4ai"
    assert calls == [
        ("regular_stealth", False, True),
        ("undetected", True, False),
    ]


@pytest.mark.asyncio
async def test_crawl4ai_progressive_enhancement_combines_undetected_and_stealth(
    monkeypatch,
):
    extractor = ArticleExtractor()
    monkeypatch.setattr(extractor, "_public_url_error", lambda url: None)
    monkeypatch.setattr(
        "src.tools.article_extractor.settings.crawl4ai_progressive_undetected_enabled",
        True,
    )
    monkeypatch.setattr(
        extractor,
        "_import_crawl4ai_core",
        lambda: (object(), object(), object(), object()),
    )
    calls = []

    async def run_attempt(url, attempt, **kwargs):
        calls.append((attempt.label, attempt.use_undetected, attempt.enable_stealth))
        if attempt.label == "undetected_stealth":
            return _success(url, "crawl4ai")
        return extractor._failure(
            url=url,
            error="blocked",
            error_code=ERROR_BLOCKED_CHALLENGE,
            method="crawl4ai",
        )

    monkeypatch.setattr(extractor, "_run_crawl4ai_attempt", run_attempt)

    result = await extractor.extract_crawl4ai_async("https://example.com/story")

    assert result.success is True
    assert result.extractor_method == "crawl4ai"
    assert calls == [
        ("regular_stealth", False, True),
        ("undetected", True, False),
        ("undetected_stealth", True, True),
    ]


@pytest.mark.asyncio
async def test_crawl4ai_403_failure_counts_as_blocked():
    extractor = ArticleExtractor()

    result = await extractor._article_from_crawl4ai_result(
        {
            "success": False,
            "status_code": 403,
            "error_message": "Access Denied",
            "html": "<html><title>Access Denied</title></html>",
        },
        url="https://example.com/story",
    )

    assert result.success is False
    assert result.extractor_method == "crawl4ai"
    assert result.error_code == ERROR_BLOCKED_CHALLENGE
    assert result.http_status == 403


def test_trafilatura_failure_falls_back_to_firecrawl_when_key_is_set(monkeypatch):
    extractor = ArticleExtractor()
    monkeypatch.setattr(extractor, "_public_url_error", lambda url: None)
    monkeypatch.setattr(
        "src.tools.article_extractor.settings.firecrawl_api_key", "fc-test"
    )
    calls = []

    def crawl4ai(url: str) -> ExtractedArticle:
        calls.append("crawl4ai")
        return _failure(extractor, url, "crawl4ai")

    def trafilatura(url: str) -> ExtractedArticle:
        calls.append("trafilatura")
        return _failure(extractor, url, "trafilatura")

    def fail_local(method: str):
        def _inner(url: str) -> ExtractedArticle:
            calls.append(method)
            return _failure(extractor, url, method)

        return _inner

    def firecrawl(url: str) -> ExtractedArticle:
        calls.append("firecrawl")
        return _success(url, "firecrawl")

    monkeypatch.setattr(
        "src.tools.article_extractor.settings.enable_selenium_fallback", True
    )
    monkeypatch.setattr(extractor, "extract_crawl4ai", crawl4ai)
    monkeypatch.setattr(extractor, "extract_trafilatura", trafilatura)
    monkeypatch.setattr(extractor, "extract_newspaper", fail_local("newspaper4k"))
    monkeypatch.setattr(extractor, "extract_fundus", fail_local("fundus"))
    monkeypatch.setattr(extractor, "extract_playwright", fail_local("playwright_sync"))
    monkeypatch.setattr(extractor, "extract_selenium", fail_local("selenium"))
    monkeypatch.setattr(extractor, "extract_firecrawl", firecrawl)

    result = extractor.extract("https://example.com/story")

    assert result.success is True
    assert result.extractor_method == "firecrawl"
    assert calls == [
        "crawl4ai",
        "trafilatura",
        "newspaper4k",
        "fundus",
        "playwright_sync",
        "selenium",
        "firecrawl",
    ]


def test_firecrawl_is_skipped_cleanly_without_api_key(monkeypatch):
    extractor = ArticleExtractor()
    monkeypatch.setattr(extractor, "_public_url_error", lambda url: None)
    monkeypatch.setattr("src.tools.article_extractor.settings.firecrawl_api_key", "")

    result = extractor.extract_firecrawl("https://example.com/story")

    assert result.success is False
    assert result.extractor_method == "firecrawl_skipped"
    assert result.error_code == ERROR_MISSING_API_KEY
    assert "FIRECRAWL_API_KEY" in (result.error or "")


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/story.html",
        "ftp://example.com/story",
        "http://localhost/story",
        "http://127.0.0.1/story",
        "http://10.0.0.5/story",
        "http://169.254.1.1/story",
        "http://[::1]/story",
    ],
)
def test_unsafe_urls_are_blocked_before_extractors(monkeypatch, url):
    extractor = ArticleExtractor()

    def fail_if_called(call_url: str) -> ExtractedArticle:
        raise AssertionError(f"extractor was called for {call_url}")

    monkeypatch.setattr(extractor, "extract_crawl4ai", fail_if_called)
    monkeypatch.setattr(extractor, "extract_trafilatura", fail_if_called)
    monkeypatch.setattr(extractor, "extract_firecrawl", fail_if_called)

    result = extractor.extract(url)

    assert result.success is False
    assert result.extractor_method == "url_guard"
    assert result.error_code == ERROR_UNSAFE_URL


@pytest.mark.asyncio
async def test_async_chain_uses_same_order(monkeypatch):
    extractor = ArticleExtractor()
    monkeypatch.setattr(extractor, "_public_url_error", lambda url: None)
    calls = []

    async def crawl4ai(url: str) -> ExtractedArticle:
        calls.append("crawl4ai")
        return _failure(extractor, url, "crawl4ai")

    async def trafilatura(url: str) -> ExtractedArticle:
        calls.append("trafilatura")
        return _failure(extractor, url, "trafilatura")

    def async_fail_local(method: str):
        async def _inner(url: str) -> ExtractedArticle:
            calls.append(method)
            return _failure(extractor, url, method)

        return _inner

    async def firecrawl(url: str) -> ExtractedArticle:
        calls.append("firecrawl")
        return _success(url, "firecrawl")

    monkeypatch.setattr(
        "src.tools.article_extractor.settings.enable_selenium_fallback", True
    )
    monkeypatch.setattr(extractor, "extract_crawl4ai_async", crawl4ai)
    monkeypatch.setattr(extractor, "extract_trafilatura_async", trafilatura)
    monkeypatch.setattr(
        extractor, "extract_newspaper_async", async_fail_local("newspaper4k")
    )
    monkeypatch.setattr(extractor, "extract_fundus_async", async_fail_local("fundus"))
    monkeypatch.setattr(
        extractor, "extract_playwright_async", async_fail_local("playwright_async")
    )
    monkeypatch.setattr(
        extractor, "extract_selenium_async", async_fail_local("selenium")
    )
    monkeypatch.setattr(extractor, "extract_firecrawl_async", firecrawl)

    result = await extractor.extract_async("https://example.com/story")

    assert result.success is True
    assert result.extractor_method == "firecrawl"
    assert calls == [
        "crawl4ai",
        "trafilatura",
        "newspaper4k",
        "fundus",
        "playwright_async",
        "selenium",
        "firecrawl",
    ]


def test_firecrawl_payload_is_normalized():
    extractor = ArticleExtractor()

    result = extractor._article_from_firecrawl_payload(
        {
            "markdown": "Firecrawl article text. " * 20,
            "html": '<html><head><meta property="og:image" content="https://example.com/card.jpg"></head></html>',
            "metadata": {
                "title": "Firecrawl title",
                "sourceURL": "https://example.com/story",
            },
            "statusCode": 200,
        },
        url="https://example.com/story",
    )

    assert result.success is True
    assert result.extractor_method == "firecrawl"
    assert result.title == "Firecrawl title"
    assert result.http_status == 200
    assert result.og_image_url == "https://example.com/card.jpg"
