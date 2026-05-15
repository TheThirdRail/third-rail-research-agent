from datetime import datetime
from unittest.mock import patch

from src.services.rss_fallback_service import RssFallbackResult
from src.services.source_aggregator_service import (
    SourceAggregatorService,
    SourceCandidate,
)
from src.tools.web_search import SearchResult


class DummySearcher:
    def __init__(self):
        self.queries = []

    def news_search(self, query: str, max_results: int = 12, time_range: str = "m"):
        self.queries.append(query)
        return [
            SearchResult(
                title="Alt Source 1",
                url="https://left.example.com/story-a",
                snippet="left",
                source="left",
            ),
            SearchResult(
                title="Alt Source 2",
                url="https://right.example.com/story-b",
                snippet="right",
                source="right",
            ),
        ]

    def web_search(self, query: str, max_results: int = 8):
        self.queries.append(f"web:{query}")
        return []


class DummyRssFallback:
    def resolve_by_url(self, url: str):
        return RssFallbackResult(
            title="China's Xi Presses Trump on Taiwan in Phone Call",
            url=url,
            summary="Xi called Taiwan the most important issue.",
            published=datetime(2026, 2, 5, 7, 24, 0),
            source_name="New York Times Politics",
            domain="nytimes.com",
            match_confidence=1.0,
            match_type="exact_url",
        )

    def resolve_by_slug(self, url: str, title_hint: str | None = None):
        return None


class NoopRssRetriever:
    def search(self, query: str, *, domains: list[str], max_results: int = 8):
        return []


def test_seed_blocked_uses_rss_metadata_for_query_enrichment(monkeypatch):
    searcher = DummySearcher()

    monkeypatch.setattr(
        SourceAggregatorService,
        "_init_searcher",
        lambda self: searcher,
    )
    monkeypatch.setattr(
        SourceAggregatorService,
        "_resolve_bias",
        lambda self, domain, url, text: None,
    )

    def fake_extract_url(self, url: str, require_success: bool = False):
        if "nytimes.com" in url:
            return SourceCandidate(
                url=url,
                domain="nytimes.com",
                title="",
                published_date=None,
                author=None,
                full_text="",
                extraction_error="Blocked by anti-bot challenge while using Crawl4AI",
                extraction_error_code="blocked_challenge",
                extractor_method="crawl4ai",
                http_status=403,
                bias_result=None,
            )

        return SourceCandidate(
            url=url,
            domain=url.split("/")[2],
            title="Recovered",
            published_date=None,
            author=None,
            full_text="x" * 800,
            extraction_error=None,
            extraction_error_code=None,
            extractor_method="trafilatura",
            http_status=None,
            bias_result=None,
        )

    monkeypatch.setattr(SourceAggregatorService, "_extract_url", fake_extract_url)

    service = SourceAggregatorService()
    service._rss_fallback = DummyRssFallback()
    service._rss_retriever = NoopRssRetriever()

    with patch("src.services.source_aggregator_service.settings") as mock_settings:
        mock_settings.retained_source_min = 2
        mock_settings.retained_source_max = 5
        mock_settings.candidate_probe_limit = 15
        mock_settings.search_time_window_days = 7
        mock_settings.rss_seed_fallback_enabled = True
        mock_settings.searxng_base_url = ""
        mock_settings.searxng_api_key = ""
        mock_settings.strict_bucket_enforcement = False
        mock_settings.max_per_exact_bias = 10
        mock_settings.max_per_bucket_group = 10
        mock_settings.allow_same_bias_backfill = True

        sources = service.gather_sources(
            description="Xi phone call taiwan",
            url="https://www.nytimes.com/2026/02/04/us/politics/xi-phone-call-taiwan.html",
        )

    assert len(sources) >= 2
    assert any("Xi Presses Trump on Taiwan" in query for query in searcher.queries)
    assert service._last_seed_context_note is not None
    assert "RSS metadata match" in service._last_seed_context_note
