import sys
import types
from datetime import datetime

from src.tools.article_extractor import ArticleExtractor


class _FakeResponse:
    status_code = 200
    text = """
    <html>
      <head>
        <title>Fallback title</title>
        <meta property="og:image" content="https://example.com/card.jpg">
      </head>
      <body><article><p>Article body</p></article></body>
    </html>
    """
    is_error = False
    url = "https://www.example.com/story"


class _FakeBody:
    def __str__(self) -> str:
        return "Fundus extracted text. " * 20


class _FakeParser:
    def parse(self, html: str, error_handling: str):
        return {
            "title": "Fundus title",
            "authors": ["Reporter"],
            "publishing_date": datetime(2026, 5, 14),
            "body": _FakeBody(),
        }


class _FakeParserProxy:
    def __call__(self, timestamp=None):
        return _FakeParser()


class _FakePublisher:
    domain = "https://www.example.com"
    request_header = {"user-agent": "fake-agent"}
    parser = _FakeParserProxy()


def _allow_public_urls(monkeypatch):
    monkeypatch.setattr(
        "src.tools.article_extractor.validate_public_http_url",
        lambda url, **kwargs: url.strip(),
    )


def test_fundus_extractor_uses_supported_publisher(monkeypatch):
    _allow_public_urls(monkeypatch)
    monkeypatch.setitem(
        sys.modules,
        "fundus",
        types.SimpleNamespace(PublisherCollection=[_FakePublisher()]),
    )
    monkeypatch.setattr(
        ArticleExtractor,
        "_safe_prefetch_html",
        lambda self, url, **kwargs: (
            _FakeResponse.text,
            _FakeResponse.status_code,
            _FakeResponse.url,
        ),
    )

    article = ArticleExtractor().extract_fundus("https://example.com/story")

    assert article.success is True
    assert article.extractor_method == "fundus"
    assert article.title == "Fundus title"
    assert article.author == "Reporter"
    assert article.og_image_url == "https://example.com/card.jpg"
    assert len(article.text) > 100


def test_fundus_extractor_reports_unsupported_publisher(monkeypatch):
    _allow_public_urls(monkeypatch)
    monkeypatch.setitem(
        sys.modules,
        "fundus",
        types.SimpleNamespace(PublisherCollection=[]),
    )

    article = ArticleExtractor().extract_fundus("https://unknown.example/story")

    assert article.success is False
    assert article.extractor_method == "fundus"
    assert article.error_code == "parse_failure"


def test_automatic_fallback_tries_fundus_before_browser(monkeypatch):
    extractor = ArticleExtractor()
    calls = []

    def failure(method: str):
        def _inner(url: str):
            calls.append(method)
            return extractor._failure(
                url=url,
                error=f"{method} failed",
                error_code="empty_content",
                method=method,
            )

        return _inner

    monkeypatch.setattr(extractor, "extract_trafilatura", failure("trafilatura"))
    monkeypatch.setattr(extractor, "extract_newspaper", failure("newspaper4k"))

    def fundus_success(url: str):
        calls.append("fundus")
        return extractor._failure(
            url=url,
            error="short",
            error_code="empty_content",
            method="fundus",
        )

    monkeypatch.setattr(extractor, "extract_fundus", fundus_success)
    monkeypatch.setattr(extractor, "extract_playwright", failure("playwright_sync"))
    monkeypatch.setattr(extractor, "extract_firecrawl", failure("firecrawl"))
    monkeypatch.setattr(
        "src.tools.article_extractor.settings.enable_selenium_fallback", False
    )

    result = extractor.extract("https://example.com/story")

    assert result.extractor_method == "firecrawl"
    assert calls == [
        "trafilatura",
        "newspaper4k",
        "fundus",
        "playwright_sync",
        "firecrawl",
    ]
