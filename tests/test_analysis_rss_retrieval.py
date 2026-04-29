from types import SimpleNamespace
from unittest.mock import patch

import httpx

from src.services.rss_retrieval_service import RssRetrievalService
from src.tools.rss_aggregator import RSSAggregator


class Entry(dict):
    published_parsed = (2026, 4, 29, 8, 0, 0, 0, 0, 0)


def test_fetch_feed_uses_bounded_http_request(monkeypatch):
    captured = {}

    class Response:
        content = b"<rss><channel><item /></channel></rss>"

        def raise_for_status(self):
            captured["status_checked"] = True

    def fake_get(url, *, timeout, follow_redirects, headers):
        captured.update(
            {
                "url": url,
                "timeout": timeout,
                "follow_redirects": follow_redirects,
                "headers": headers,
            }
        )
        return Response()

    def fake_parse(content):
        captured["content"] = content
        return SimpleNamespace(
            entries=[
                Entry(
                    title="RSS headline",
                    link="https://example.com/story",
                    summary="RSS summary",
                )
            ]
        )

    monkeypatch.setattr("src.tools.rss_aggregator.httpx.get", fake_get)
    monkeypatch.setattr("src.tools.rss_aggregator.feedparser.parse", fake_parse)

    aggregator = RSSAggregator(feeds_config_path="missing.yaml")
    items = aggregator.fetch_feed(
        "https://feeds.example.com/rss",
        timeout_seconds=2,
        source_name="Example",
    )

    assert captured["url"] == "https://feeds.example.com/rss"
    assert captured["timeout"] == 2
    assert captured["follow_redirects"] is True
    assert captured["headers"]["User-Agent"] == "ResearchAgent/1.0"
    assert captured["status_checked"] is True
    assert captured["content"] == Response.content
    assert items[0].title == "RSS headline"
    assert items[0].source_name == "Example"


def test_fetch_feed_returns_empty_on_timeout(monkeypatch):
    def fake_get(*args, **kwargs):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr("src.tools.rss_aggregator.httpx.get", fake_get)

    aggregator = RSSAggregator(feeds_config_path="missing.yaml")

    assert aggregator.fetch_feed("https://feeds.example.com/rss", timeout_seconds=1) == []


def test_rss_retrieval_caps_feed_attempts_and_passes_timeout():
    class FakeAggregator:
        feeds = [
            {"url": f"https://feeds{i}.example.com/rss", "name": "Target News"}
            for i in range(5)
        ]

        def __init__(self):
            self.calls = []

        def fetch_feed(self, **kwargs):
            self.calls.append(kwargs)
            return []

    aggregator = FakeAggregator()
    service = RssRetrievalService(aggregator=aggregator)

    with patch("src.services.rss_retrieval_service.settings") as mock_settings:
        mock_settings.analysis_rss_max_feeds_per_bucket = 2
        mock_settings.analysis_rss_timeout_seconds = 4

        results = service.search(
            "target story",
            domains=["target.example.com"],
            max_results=8,
        )

    assert results == []
    assert len(aggregator.calls) == 2
    assert {call["timeout_seconds"] for call in aggregator.calls} == {4}
