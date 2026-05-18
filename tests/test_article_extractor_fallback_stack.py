import json
import sys
import types

import pytest

from src.tools.article_extractor import (
    ERROR_BLOCKED_CHALLENGE,
    ERROR_MISSING_API_KEY,
    ERROR_PARSE_FAILURE,
    ERROR_PAYWALL_OR_SUBSCRIPTION,
    ERROR_SHORT_CONTENT,
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
        "src.tools.article_extractor.settings."
        "crawl4ai_progressive_undetected_enabled",
        True,
    )
    monkeypatch.setattr(
        extractor,
        "_import_crawl4ai_core",
        lambda: (object(), object(), object(), object()),
    )
    calls = []

    async def run_attempt(url, attempt, profile, **kwargs):
        calls.append(
            (
                attempt.label,
                attempt.use_undetected,
                attempt.enable_stealth,
                profile.label,
            )
        )
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
        ("regular_stealth", False, True, "default_news"),
        ("undetected", True, False, "protected_news"),
    ]


@pytest.mark.asyncio
async def test_crawl4ai_progressive_enhancement_combines_undetected_and_stealth(
    monkeypatch,
):
    extractor = ArticleExtractor()
    monkeypatch.setattr(extractor, "_public_url_error", lambda url: None)
    monkeypatch.setattr(
        "src.tools.article_extractor.settings."
        "crawl4ai_progressive_undetected_enabled",
        True,
    )
    monkeypatch.setattr(
        extractor,
        "_import_crawl4ai_core",
        lambda: (object(), object(), object(), object()),
    )
    calls = []

    async def run_attempt(url, attempt, profile, **kwargs):
        calls.append(
            (
                attempt.label,
                attempt.use_undetected,
                attempt.enable_stealth,
                profile.label,
            )
        )
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
        ("regular_stealth", False, True, "default_news"),
        ("undetected", True, False, "protected_news"),
        ("undetected_stealth", True, True, "protected_news"),
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


@pytest.mark.asyncio
async def test_crawl4ai_429_and_captcha_count_as_blocked():
    extractor = ArticleExtractor()

    result = await extractor._article_from_crawl4ai_result(
        {
            "success": False,
            "status_code": 429,
            "error_message": "captcha required",
            "html": "<html><title>Verify you are human</title></html>",
        },
        url="https://example.com/story",
    )

    assert result.success is False
    assert result.error_code == ERROR_BLOCKED_CHALLENGE
    assert result.http_status == 429


def test_paywall_language_is_classified():
    extractor = ArticleExtractor()

    result = extractor._article_from_firecrawl_payload(
        {
            "markdown": "Sign in to continue reading this subscriber-only article.",
            "statusCode": 200,
        },
        url="https://example.com/story",
    )

    assert result.success is False
    assert result.error_code == ERROR_PAYWALL_OR_SUBSCRIPTION


@pytest.mark.asyncio
async def test_short_successful_crawl4ai_output_is_classified():
    extractor = ArticleExtractor()

    result = await extractor._article_from_crawl4ai_result(
        {
            "success": True,
            "status_code": 200,
            "markdown": "Too short.",
        },
        url="https://example.com/story",
    )

    assert result.success is False
    assert result.error_code == ERROR_SHORT_CONTENT


@pytest.mark.asyncio
async def test_crawl4ai_short_output_tries_dynamic_profile(monkeypatch):
    extractor = ArticleExtractor()
    monkeypatch.setattr(extractor, "_public_url_error", lambda url: None)
    monkeypatch.setattr(
        extractor,
        "_import_crawl4ai_core",
        lambda: (object(), object(), object(), object()),
    )
    calls = []

    async def run_attempt(url, attempt, profile, **kwargs):
        calls.append((attempt.label, profile.label))
        if profile.label == "dynamic_news":
            return _success(url, "crawl4ai")
        return extractor._failure(
            url=url,
            error="short",
            error_code=ERROR_SHORT_CONTENT,
            method="crawl4ai",
        )

    monkeypatch.setattr(extractor, "_run_crawl4ai_attempt", run_attempt)

    result = await extractor.extract_crawl4ai_async("https://example.com/story")

    assert result.success is True
    assert calls == [
        ("regular_stealth", "default_news"),
        ("regular_stealth", "dynamic_news"),
    ]


@pytest.mark.asyncio
async def test_crawl4ai_parse_failure_does_not_burn_protected_attempts(monkeypatch):
    extractor = ArticleExtractor()
    monkeypatch.setattr(extractor, "_public_url_error", lambda url: None)
    monkeypatch.setattr(
        extractor,
        "_import_crawl4ai_core",
        lambda: (object(), object(), object(), object()),
    )
    calls = []

    async def run_attempt(url, attempt, profile, **kwargs):
        calls.append((attempt.label, profile.label))
        return extractor._failure(
            url=url,
            error="parse failed",
            error_code=ERROR_PARSE_FAILURE,
            method="crawl4ai",
        )

    monkeypatch.setattr(extractor, "_run_crawl4ai_attempt", run_attempt)

    result = await extractor.extract_crawl4ai_async("https://example.com/story")

    assert result.success is False
    assert result.error_code == ERROR_PARSE_FAILURE
    assert calls == [("regular_stealth", "default_news")]


def test_json_ld_newsarticle_body_is_accepted():
    extractor = ArticleExtractor()
    body = "Structured article body. " * 12
    html = (
        '<html><head><script type="application/ld+json">'
        + json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "NewsArticle",
                "headline": "JSON-LD headline",
                "author": {"name": "Reporter Name"},
                "datePublished": "2026-05-18T12:00:00+00:00",
                "articleBody": body,
                "image": {"url": "https://example.com/image.jpg"},
            }
        )
        + "</script></head><body></body></html>"
    )

    result = extractor._extract_from_html(
        url="https://example.com/story",
        html_content=html,
        method="test",
    )

    assert result.success is True
    assert result.title == "JSON-LD headline"
    assert result.author == "Reporter Name"
    assert result.text == body.strip()
    assert result.og_image_url == "https://example.com/image.jpg"


def test_json_ld_nested_graph_is_accepted():
    extractor = ArticleExtractor()
    body = "Nested structured article body. " * 12
    html = (
        '<script type="application/ld+json">'
        + json.dumps(
            {
                "@context": "https://schema.org",
                "@graph": [
                    {"@type": "WebSite", "name": "Example"},
                    {
                        "@type": "BlogPosting",
                        "headline": "Nested headline",
                        "articleBody": body,
                    },
                ],
            }
        )
        + "</script>"
    )

    result = extractor._extract_from_html(
        url="https://example.com/story",
        html_content=html,
        method="test",
    )

    assert result.success is True
    assert result.title == "Nested headline"
    assert result.text == body.strip()


def test_malformed_json_ld_falls_back_to_html_extraction(monkeypatch):
    extractor = ArticleExtractor()
    module = types.ModuleType("trafilatura")
    module.extract = lambda *args, **kwargs: "Fallback body. " * 20
    module.extract_metadata = lambda html: types.SimpleNamespace(
        title="Fallback title",
        author=None,
        date=None,
    )
    monkeypatch.setitem(sys.modules, "trafilatura", module)

    result = extractor._extract_from_html(
        url="https://example.com/story",
        html_content='<script type="application/ld+json">{ bad json }</script>',
        method="test",
    )

    assert result.success is True
    assert result.title == "Fallback title"
    assert result.text.startswith("Fallback body.")


def test_short_json_ld_body_falls_back_to_html_extraction(monkeypatch):
    extractor = ArticleExtractor()
    module = types.ModuleType("trafilatura")
    module.extract = lambda *args, **kwargs: "Fallback body. " * 20
    module.extract_metadata = lambda html: types.SimpleNamespace(
        title="Fallback title",
        author=None,
        date=None,
    )
    monkeypatch.setitem(sys.modules, "trafilatura", module)
    html = (
        '<script type="application/ld+json">'
        + json.dumps({"@type": "NewsArticle", "articleBody": "short"})
        + "</script>"
    )

    result = extractor._extract_from_html(
        url="https://example.com/story",
        html_content=html,
        method="test",
    )

    assert result.success is True
    assert result.title == "Fallback title"
    assert result.text.startswith("Fallback body.")


def test_local_stack_failure_falls_back_to_firecrawl_when_key_is_set(monkeypatch):
    extractor = ArticleExtractor()
    monkeypatch.setattr(extractor, "_public_url_error", lambda url: None)
    monkeypatch.setattr("src.tools.article_extractor.settings.firecrawl_api_key", "fc-test")
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

    monkeypatch.setattr(extractor, "extract_crawl4ai", crawl4ai)
    monkeypatch.setattr(extractor, "extract_trafilatura", trafilatura)
    monkeypatch.setattr(extractor, "extract_playwright", fail_local("playwright_sync"))
    monkeypatch.setattr(extractor, "extract_firecrawl", firecrawl)

    result = extractor.extract("https://example.com/story")

    assert result.success is True
    assert result.extractor_method == "firecrawl"
    assert calls == [
        "crawl4ai",
        "trafilatura",
        "playwright_sync",
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

    monkeypatch.setattr(extractor, "extract_crawl4ai_async", crawl4ai)
    monkeypatch.setattr(extractor, "extract_trafilatura_async", trafilatura)
    monkeypatch.setattr(
        extractor, "extract_playwright_async", async_fail_local("playwright_async")
    )
    monkeypatch.setattr(extractor, "extract_firecrawl_async", firecrawl)

    result = await extractor.extract_async("https://example.com/story")

    assert result.success is True
    assert result.extractor_method == "firecrawl"
    assert calls == [
        "crawl4ai",
        "trafilatura",
        "playwright_async",
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


def test_firecrawl_first_call_uses_upgraded_options(monkeypatch):
    extractor = ArticleExtractor()
    calls = []

    class FakeFirecrawl:
        def __init__(self, api_key):
            self.api_key = api_key

        def scrape(self, **kwargs):
            calls.append(kwargs)
            return {"markdown": "Firecrawl body. " * 20, "statusCode": 200}

    module = types.ModuleType("firecrawl")
    module.Firecrawl = FakeFirecrawl
    module.FirecrawlApp = None
    monkeypatch.setitem(sys.modules, "firecrawl", module)
    monkeypatch.setattr("src.tools.article_extractor.settings.firecrawl_api_key", "fc")

    result = extractor.extract_firecrawl("https://example.com/story")

    assert result.success is True
    assert calls[0]["formats"] == ["markdown", "html", "rawHtml", "links"]
    assert calls[0]["only_main_content"] is True
    assert calls[0]["wait_for"] > 0
    assert calls[0]["location"]["country"] == "US"
    assert calls[0]["remove_base64_images"] is True
    assert calls[0]["block_ads"] is True
    assert calls[0]["max_age"] == 0


def test_firecrawl_short_output_retries_without_main_content(monkeypatch):
    extractor = ArticleExtractor()
    calls = []

    class FakeFirecrawl:
        def __init__(self, api_key):
            self.api_key = api_key

        def scrape(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return {"markdown": "short", "statusCode": 200}
            return {"markdown": "Recovered Firecrawl body. " * 20, "statusCode": 200}

    module = types.ModuleType("firecrawl")
    module.Firecrawl = FakeFirecrawl
    module.FirecrawlApp = None
    monkeypatch.setitem(sys.modules, "firecrawl", module)
    monkeypatch.setattr("src.tools.article_extractor.settings.firecrawl_api_key", "fc")

    result = extractor.extract_firecrawl("https://example.com/story")

    assert result.success is True
    assert len(calls) == 2
    assert calls[0]["only_main_content"] is True
    assert calls[1]["only_main_content"] is False
    assert "proxy" not in calls[1]


def test_firecrawl_blocked_output_retries_with_proxy_auto_when_enabled(monkeypatch):
    extractor = ArticleExtractor()
    calls = []

    class FakeFirecrawl:
        def __init__(self, api_key):
            self.api_key = api_key

        def scrape(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return {"markdown": "Access denied captcha", "statusCode": 403}
            return {"markdown": "Recovered Firecrawl body. " * 20, "statusCode": 200}

    module = types.ModuleType("firecrawl")
    module.Firecrawl = FakeFirecrawl
    module.FirecrawlApp = None
    monkeypatch.setitem(sys.modules, "firecrawl", module)
    monkeypatch.setattr("src.tools.article_extractor.settings.firecrawl_api_key", "fc")
    monkeypatch.setattr(
        "src.tools.article_extractor.settings.firecrawl_proxy_auto_enabled",
        True,
    )

    result = extractor.extract_firecrawl("https://example.com/story")

    assert result.success is True
    assert len(calls) == 2
    assert calls[1]["only_main_content"] is False
    assert calls[1]["proxy"] == "auto"


def test_firecrawl_blocked_output_skips_proxy_auto_when_disabled(monkeypatch):
    extractor = ArticleExtractor()
    calls = []

    class FakeFirecrawl:
        def __init__(self, api_key):
            self.api_key = api_key

        def scrape(self, **kwargs):
            calls.append(kwargs)
            return {"markdown": "Access denied captcha", "statusCode": 403}

    module = types.ModuleType("firecrawl")
    module.Firecrawl = FakeFirecrawl
    module.FirecrawlApp = None
    monkeypatch.setitem(sys.modules, "firecrawl", module)
    monkeypatch.setattr("src.tools.article_extractor.settings.firecrawl_api_key", "fc")
    monkeypatch.setattr(
        "src.tools.article_extractor.settings.firecrawl_proxy_auto_enabled",
        False,
    )

    result = extractor.extract_firecrawl("https://example.com/story")

    assert result.success is False
    assert result.error_code == ERROR_BLOCKED_CHALLENGE
    assert len(calls) == 1


def test_firecrawl_raw_html_is_used_as_html_fallback():
    extractor = ArticleExtractor()
    body = "Raw HTML structured body. " * 12
    html = (
        '<script type="application/ld+json">'
        + json.dumps(
            {
                "@type": "NewsArticle",
                "headline": "Raw HTML headline",
                "articleBody": body,
            }
        )
        + "</script>"
    )

    result = extractor._article_from_firecrawl_payload(
        {
            "rawHtml": html,
            "metadata": {"sourceURL": "https://example.com/story"},
            "statusCode": 200,
        },
        url="https://example.com/story",
    )

    assert result.success is True
    assert result.extractor_method == "firecrawl"
    assert result.title == "Raw HTML headline"
    assert result.text == body.strip()
