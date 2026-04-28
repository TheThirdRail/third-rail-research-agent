from datetime import datetime

from src.services.rss_fallback_service import RssFallbackService
from src.tools.rss_aggregator import FeedItem


def test_resolve_by_url_exact_match(monkeypatch):
    service = RssFallbackService()

    monkeypatch.setattr(
        service,
        "get_candidate_feeds_for_domain",
        lambda domain: [{"url": "https://rss.example.com", "name": "Example"}],
    )
    monkeypatch.setattr(
        service,
        "_iter_feed_items",
        lambda feeds, max_items=80: [
            FeedItem(
                title="Exact Story",
                url="https://example.com/story",
                domain="example.com",
                published=datetime(2026, 2, 5, 12, 0, 0),
                summary="Summary",
                bias=0,
                source_name="Example",
            )
        ],
    )

    result = service.resolve_by_url("https://example.com/story")

    assert result is not None
    assert result.title == "Exact Story"
    assert result.match_type == "exact_url"
    assert result.match_confidence == 1.0


def test_resolve_by_slug_uses_title_hint(monkeypatch):
    service = RssFallbackService()

    monkeypatch.setattr(
        service,
        "get_candidate_feeds_for_domain",
        lambda domain: [{"url": "https://rss.nytimes.com", "name": "New York Times"}],
    )
    monkeypatch.setattr(
        service,
        "_iter_feed_items",
        lambda feeds, max_items=80: [
            FeedItem(
                title="China’s Xi Presses Trump on Taiwan in Phone Call",
                url="https://www.nytimes.com/2026/02/04/us/politics/xi-phone-call-taiwan.html",
                domain="nytimes.com",
                published=datetime(2026, 2, 5, 7, 24, 0),
                summary="Both leaders gave versions of what they discussed.",
                bias=-2,
                source_name="New York Times Politics",
            )
        ],
    )

    result = service.resolve_by_slug(
        "https://www.nytimes.com/2026/02/04/us/politics/xi-phone-call-taiwan.html",
        title_hint="Xi Presses Trump on Taiwan",
    )

    assert result is not None
    assert result.domain == "nytimes.com"
    assert result.match_type == "slug_title"
    assert result.match_confidence >= 0.45
