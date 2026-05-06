from unittest.mock import patch

import pytest

from src.core.exceptions import SourceExtractionError
from src.services.balanced_source_planner import BalancedSourcePlanner
from src.services.source_aggregator_service import (
    QueryAttempt,
    SourceAggregatorService,
    SourceCandidate,
)
from src.tools.bias_classifier import BiasResult
from src.tools.web_search import SearchResult


def bias(domain: str, value: int, label: str) -> BiasResult:
    return BiasResult(
        domain=domain,
        bias=value,
        bias_label=label,
        confidence=1.0,
        method="dataset",
        factual_rating="high",
        category="mainstream",
    )


def candidate(domain: str, value: int, label: str) -> SourceCandidate:
    return SourceCandidate(
        url=f"https://{domain}/story",
        domain=domain,
        title=f"{domain} story",
        published_date=None,
        author=None,
        full_text="story text" * 50,
        extraction_error=None,
        bias_result=bias(domain, value, label),
    )


class NoopRssRetriever:
    def search(self, query: str, *, domains: list[str], max_results: int = 8):
        return []


def test_minus_one_counts_left_and_plus_one_counts_right():
    service = SourceAggregatorService()
    sources = [
        candidate("slight-left.example", -1, "Slight Left"),
        candidate("slight-right.example", 1, "Slight Right"),
        candidate("center.example", 0, "Center"),
    ]

    coverage = service.summarize_coverage(sources)

    assert coverage["left_count"] == 1
    assert coverage["center_count"] == 1
    assert coverage["right_count"] == 1


def test_missing_required_right_side_fails_by_default(monkeypatch):
    class DummySearcher:
        def news_search(self, query: str, max_results: int = 10, time_range: str = "w"):
            return [
                SearchResult("Left A", "https://left-a.example/story", "", "left"),
                SearchResult("Left B", "https://left-b.example/story", "", "left"),
            ]

        def web_search(self, query: str, max_results: int = 10):
            return []

    def fake_extract_url(self, url: str, require_success: bool = False):
        domain = url.split("/")[2].replace("www.", "")
        return candidate(domain, -1, "Slight Left")

    monkeypatch.setattr(
        SourceAggregatorService, "_init_searcher", lambda self: DummySearcher()
    )
    monkeypatch.setattr(SourceAggregatorService, "_extract_url", fake_extract_url)

    service = SourceAggregatorService()
    service._rss_retriever = NoopRssRetriever()

    with patch("src.services.source_aggregator_service.settings") as mock_settings:
        mock_settings.retained_source_min = 1
        mock_settings.retained_source_max = 5
        mock_settings.candidate_probe_limit = 10
        mock_settings.search_time_window_days = 7
        mock_settings.strict_bucket_enforcement = True
        mock_settings.required_bucket_groups = "left_side,right_side"
        mock_settings.max_per_exact_bias = 1
        mock_settings.max_per_bucket_group = 2
        mock_settings.allow_same_bias_backfill = False
        with pytest.raises(SourceExtractionError, match="right_side"):
            service.gather_sources("left-only story", None)


def test_exact_bias_cap_rejects_duplicate_bias():
    service = SourceAggregatorService()
    sources = [candidate("first-left.example", -1, "Slight Left")]
    duplicate = candidate("second-left.example", -1, "Slight Left")

    with patch("src.services.source_aggregator_service.settings") as mock_settings:
        mock_settings.max_per_exact_bias = 1
        mock_settings.max_per_bucket_group = 2
        assert not service._candidate_allowed_by_policy(duplicate, sources)


def test_rss_retrieval_runs_before_site_search():
    calls: list[str] = []

    class FakeRss:
        def search(self, query: str, *, domains: list[str], max_results: int = 8):
            calls.append("rss")
            return [SearchResult("RSS story", "https://rss.example/story", "", "rss")]

    class FakeSearcher:
        def web_search(self, query: str, max_results: int = 10):
            calls.append("site")
            return []

        def news_search(self, query: str, max_results: int = 10, time_range: str = "w"):
            calls.append("open_web")
            return []

    service = SourceAggregatorService()
    service._rss_retriever = FakeRss()
    service._searcher = FakeSearcher()
    plan = BalancedSourcePlanner().plan(seed_bias=0)

    service._search_queries([QueryAttempt(query="test story", family="lexical")], plan)

    assert calls[0] == "rss"
    assert "site" in calls


def test_rss_retrieval_can_be_disabled_for_analysis_runtime():
    calls: list[str] = []

    class FakeRss:
        def search(self, query: str, *, domains: list[str], max_results: int = 8):
            calls.append("rss")
            return []

    class FakeSearcher:
        def web_search(self, query: str, max_results: int = 10):
            calls.append("site")
            return []

        def news_search(self, query: str, max_results: int = 10, time_range: str = "w"):
            calls.append("open_web")
            return []

    service = SourceAggregatorService()
    service._rss_retriever = FakeRss()
    service._searcher = FakeSearcher()
    plan = BalancedSourcePlanner().plan(seed_bias=0)

    with patch("src.services.source_aggregator_service.settings") as mock_settings:
        mock_settings.analysis_rss_first_enabled = False
        mock_settings.candidate_probe_limit = 15
        mock_settings.search_time_window_days = 7

        service._search_queries(
            [QueryAttempt(query="test story", family="lexical")], plan
        )

    assert "rss" not in calls
    assert "site" in calls
