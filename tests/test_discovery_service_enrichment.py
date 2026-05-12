import time
from datetime import datetime
from threading import Lock

from src.services.discovery_service import DiscoveryService
from src.tools.rss_aggregator import FeedItem
from src.tools.web_search import SearchResult


class DummySearcher:
    def news_search(self, query: str, max_results: int = 10, time_range: str = "w"):
        return [
            SearchResult(
                title="Search Found Story",
                url="https://example.com/search-story",
                snippet="search snippet",
                source="example",
            )
        ]


def test_prefetch_discovery_enrichment_when_rss_sparse(monkeypatch):
    service = DiscoveryService()

    monkeypatch.setattr(
        "src.services.discovery_service.RSSAggregator.search_feeds",
        lambda self, keywords, max_age_hours=48, max_per_feed=10: [
            FeedItem(
                title="One RSS Story",
                url="https://rss.example.com/one",
                domain="rss.example.com",
                published=datetime(2026, 2, 5, 12, 0, 0),
                summary="rss summary",
                bias=0,
                source_name="RSS",
            )
        ],
    )
    monkeypatch.setattr(
        "src.services.discovery_service._get_searcher", lambda: DummySearcher()
    )
    monkeypatch.setattr(
        "src.services.discovery_service.blocked_public_url_reason",
        lambda url: "",
    )

    def fake_extract(self, url: str):
        from src.tools.article_extractor import ExtractedArticle

        return ExtractedArticle(
            title="Extracted Search Story",
            text="x" * 600,
            author=None,
            date=None,
            domain="example.com",
            url=url,
            success=True,
            error=None,
            error_code=None,
            extractor_method="playwright_async",
        )

    monkeypatch.setattr(
        "src.services.discovery_service.ArticleExtractor.extract", fake_extract
    )

    context = service._prefetch_discovery_context(["politics", "taiwan"], count=5)

    assert "One RSS Story" in context
    assert "Extracted Search Story" in context
    assert "Method: playwright_async" in context


def test_prefetch_discovery_skips_unsafe_search_result(monkeypatch):
    service = DiscoveryService()

    monkeypatch.setattr(
        "src.services.discovery_service.RSSAggregator.search_feeds",
        lambda self, keywords, max_age_hours=48, max_per_feed=10: [],
    )
    monkeypatch.setattr(
        "src.services.discovery_service._get_searcher", lambda: DummySearcher()
    )
    monkeypatch.setattr(
        "src.services.discovery_service.blocked_public_url_reason",
        lambda url: "blocked_private_or_local_url",
    )

    def fail_extract(self, url: str):
        raise AssertionError("unsafe URL reached article extraction")

    monkeypatch.setattr(
        "src.services.discovery_service.ArticleExtractor.extract",
        fail_extract,
    )

    context = service._prefetch_discovery_context(["politics"], count=2)

    assert "Search Found Story" not in context


def test_prefetch_discovery_extracts_search_results_concurrently(monkeypatch):
    service = DiscoveryService()

    monkeypatch.setattr(
        "src.services.discovery_service.RSSAggregator.search_feeds",
        lambda self, keywords, max_age_hours=48, max_per_feed=10: [],
    )
    monkeypatch.setattr(
        "src.services.discovery_service.blocked_public_url_reason",
        lambda url: "",
    )

    class SlowSearcher:
        def news_search(self, query: str, max_results: int = 10, time_range: str = "w"):
            return [
                SearchResult(
                    title=f"Search Story {idx}",
                    url=f"https://example{idx}.com/story",
                    snippet="search snippet",
                    source=f"example{idx}",
                )
                for idx in range(4)
            ]

    monkeypatch.setattr(
        "src.services.discovery_service._get_searcher", lambda: SlowSearcher()
    )

    active = 0
    max_active = 0
    lock = Lock()

    def fake_extract(self, url: str):
        nonlocal active, max_active
        from src.tools.article_extractor import ExtractedArticle

        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1

        return ExtractedArticle(
            title=f"Extracted {url}",
            text="x" * 600,
            author=None,
            date=None,
            domain=url.split("/")[2],
            url=url,
            success=True,
            error=None,
            error_code=None,
            extractor_method="test",
        )

    monkeypatch.setattr(
        "src.services.discovery_service.ArticleExtractor.extract", fake_extract
    )

    started_at = time.perf_counter()
    context = service._prefetch_discovery_context(["politics"], count=4)
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.16
    assert max_active > 1
    assert context.index("https://example0.com/story") < context.index(
        "https://example3.com/story"
    )


def test_discover_passes_prefetched_context_to_crew(monkeypatch):
    service = DiscoveryService()

    monkeypatch.setattr(
        "src.services.discovery_service.settings.discovery_enrichment_enabled", True
    )
    monkeypatch.setattr(
        service, "_prefetch_discovery_context", lambda topics, count: "PREFETCH"
    )

    captured = {}

    def fake_run_discovery(channel_topics, count=10, prefetched_context=None):
        captured["prefetched_context"] = prefetched_context
        return {"raw_output": "ok", "topics_searched": channel_topics}

    monkeypatch.setattr(
        "src.services.discovery_service.run_discovery", fake_run_discovery
    )

    result = service.discover(["news"], count=4)

    assert result["raw_output"] == "ok"
    assert captured["prefetched_context"] == "PREFETCH"
