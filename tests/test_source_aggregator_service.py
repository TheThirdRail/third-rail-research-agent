from unittest.mock import patch
from urllib.parse import urlparse

from src.services.source_aggregator_service import (
    SourceAggregatorService,
    SourceCandidate,
)
from src.tools.web_search import SearchResult


def test_gather_sources_continues_when_seed_url_unextractable(monkeypatch):
    class DummySearcher:
        def news_search(self, query: str, max_results: int = 10, time_range: str = "m"):
            return [
                SearchResult(
                    title="Left source",
                    url="https://left.example.com/story-a",
                    snippet="left snippet",
                    source="left",
                ),
                SearchResult(
                    title="Right source",
                    url="https://right.example.com/story-b",
                    snippet="right snippet",
                    source="right",
                ),
                SearchResult(
                    title="Center source",
                    url="https://center.example.com/story-c",
                    snippet="center snippet",
                    source="center",
                ),
            ]

        def web_search(self, query: str, max_results: int = 10):
            return []

    monkeypatch.setattr(
        SourceAggregatorService, "_init_searcher", lambda self: DummySearcher()
    )
    monkeypatch.setattr(
        SourceAggregatorService,
        "_resolve_bias",
        lambda self, domain, url, text: None,
    )

    def fake_extract_url(
        self, url: str, require_success: bool = False
    ) -> SourceCandidate:
        domain = urlparse(url).netloc.replace("www.", "")
        if "nytimes.com" in domain:
            return SourceCandidate(
                url=url,
                domain=domain,
                title="",
                published_date=None,
                author=None,
                full_text="",
                extraction_error="No content extracted via Playwright",
                bias_result=None,
            )
        return SourceCandidate(
            url=url,
            domain=domain,
            title="Recovered source",
            published_date=None,
            author=None,
            full_text="x" * 500,
            extraction_error=None,
            bias_result=None,
        )

    monkeypatch.setattr(SourceAggregatorService, "_extract_url", fake_extract_url)

    # Override retained_source_min to match test fixture (3 available search results)
    with patch("src.services.source_aggregator_service.settings") as mock_settings:
        mock_settings.retained_source_min = 2
        mock_settings.retained_source_max = 15
        mock_settings.candidate_probe_limit = 50
        mock_settings.rss_seed_fallback_enabled = True
        mock_settings.searxng_base_url = ""
        mock_settings.searxng_api_key = ""

        service = SourceAggregatorService()
        sources = service.gather_sources(
            description="Xi phone call taiwan",
            url="https://www.nytimes.com/2026/02/04/us/politics/xi-phone-call-taiwan.html",
        )

    assert len(sources) >= 2
    assert all(src.full_text for src in sources)
    assert all("nytimes.com" not in src.domain for src in sources)

