from types import SimpleNamespace
from unittest.mock import patch

import httpx

from src.schemas.story_packet import StoryPacket
from src.services.balanced_source_planner import BucketSpec
from src.services.rss_retrieval_service import RssRetrievalService
from src.tools.rss_aggregator import FeedItem, RSSAggregator


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
    monkeypatch.setattr(
        "src.tools.rss_aggregator.blocked_public_url_reason",
        lambda url: "",
    )

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


def test_fetch_feed_skips_private_item_links(monkeypatch):
    class Response:
        content = b"<rss><channel><item /></channel></rss>"

        def raise_for_status(self):
            pass

    def fake_parse(content):
        return SimpleNamespace(
            entries=[
                Entry(
                    title="Internal link",
                    link="http://127.0.0.1/private",
                    summary="RSS summary",
                )
            ]
        )

    monkeypatch.setattr(
        "src.tools.rss_aggregator.httpx.get",
        lambda *args, **kwargs: Response(),
    )
    monkeypatch.setattr("src.tools.rss_aggregator.feedparser.parse", fake_parse)

    aggregator = RSSAggregator(feeds_config_path="missing.yaml")

    assert aggregator.fetch_feed("https://feeds.example.com/rss") == []


def test_fetch_feed_returns_empty_on_timeout(monkeypatch):
    def fake_get(*args, **kwargs):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr("src.tools.rss_aggregator.httpx.get", fake_get)

    aggregator = RSSAggregator(feeds_config_path="missing.yaml")

    assert (
        aggregator.fetch_feed("https://feeds.example.com/rss", timeout_seconds=1) == []
    )


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


def test_search_story_rejects_must_not_have_wrong_event():
    class FakeAggregator:
        feeds = [{"url": "https://feeds.example.com/rss", "name": "Target News"}]

        def fetch_feed(self, **kwargs):
            return [
                FeedItem(
                    title="Mayor announces unrelated budget plan",
                    url="https://target.example.com/budget",
                    domain="target.example.com",
                    published=None,
                    summary="Mayor Jane Doe discusses the 2025 budget proposal.",
                    bias=0,
                    source_name="Target News",
                )
            ]

    service = RssRetrievalService(aggregator=FakeAggregator())
    packet = StoryPacket(
        canonical_headline="Mayor Jane Doe vetoes transit bill",
        actors=["Jane Doe"],
        action_verbs=["vetoes"],
        distinctive_terms=["transit bill"],
        must_not_have_terms=["budget proposal"],
    )
    bucket = BucketSpec(
        label="center",
        bias_values={0},
        required=False,
        domain_targets=["target.example.com"],
    )

    assert service.search_story(packet, bucket) == []


def test_search_story_accepts_same_event_with_distinctive_markers():
    class FakeAggregator:
        feeds = [{"url": "https://feeds.example.com/rss", "name": "Target News"}]

        def fetch_feed(self, **kwargs):
            return [
                FeedItem(
                    title="Jane Doe rejects transit legislation after 8647 post",
                    url="https://target.example.com/transit",
                    domain="target.example.com",
                    published=None,
                    summary="The mayor vetoed the transit bill after debate on X.",
                    bias=0,
                    source_name="Target News",
                )
            ]

    service = RssRetrievalService(aggregator=FakeAggregator())
    packet = StoryPacket(
        canonical_headline="Mayor Jane Doe vetoes transit bill after 8647 post",
        actors=["Jane Doe"],
        action_verbs=["vetoed", "vetoes", "rejects"],
        distinctive_terms=["transit bill", "8647", "X"],
    )
    bucket = BucketSpec(
        label="center",
        bias_values={0},
        required=False,
        domain_targets=["target.example.com"],
    )

    results = service.search_story(packet, bucket)

    assert [result.url for result in results] == ["https://target.example.com/transit"]
