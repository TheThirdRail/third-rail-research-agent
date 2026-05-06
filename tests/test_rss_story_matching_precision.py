"""Tests for RSS story-matching precision.

Verifies the RSS scoring system correctly:
- Accepts high-confidence same-story items
- Rejects same actor / wrong event
- Rejects same topic / wrong date
- Handles distinctive marker matches
- Rejects via must-not-have terms
"""

from datetime import UTC, datetime

from src.schemas.story_packet import StoryPacket
from src.services.rss_retrieval_service import RssRetrievalService
from src.tools.rss_aggregator import FeedItem


def _make_packet(**overrides: object) -> StoryPacket:
    """Build a test StoryPacket with sensible defaults."""
    defaults: dict[str, object] = {
        "canonical_headline": "Senator Smith vetoes education funding bill",
        "actors": ["Senator Smith", "Smith"],
        "action_verbs": ["vetoes", "vetoed", "blocked"],
        "distinctive_terms": ["education funding bill", "HR-4521"],
        "number_markers": ["HR-4521"],
        "must_not_have_terms": ["healthcare", "immigration"],
        "time_window_start": datetime(2026, 4, 15, tzinfo=UTC),
        "time_window_end": datetime(2026, 4, 20, tzinfo=UTC),
    }
    defaults.update(overrides)
    return StoryPacket(**defaults)  # type: ignore[arg-type]


def _make_item(
    title: str = "",
    summary: str = "",
    published: datetime | None = None,
) -> FeedItem:
    """Build a test FeedItem."""
    return FeedItem(
        title=title,
        url="https://example.com/article",
        domain="example.com",
        published=published or datetime(2026, 4, 17, tzinfo=UTC),
        summary=summary,
        bias=0,
        source_name="Example News",
    )


def _score(item: FeedItem, packet: StoryPacket) -> float:
    """Score a single feed item against a story packet."""
    service = RssRetrievalService.__new__(RssRetrievalService)
    return service._score_story_item(item, packet)


class TestHighConfidenceAcceptance:
    """Items clearly about the same story should score highly."""

    def test_matching_headline_scores_high(self):
        """An item with matching headline and actors scores well."""
        packet = _make_packet()
        item = _make_item(
            title="Senator Smith vetoes education funding bill",
            summary="The bill HR-4521 was vetoed.",
        )
        score = _score(item, packet)
        assert score >= 0.45, f"Expected high score, got {score}"

    def test_matching_headline_with_marker(self):
        """Marker overlap boosts score."""
        packet = _make_packet()
        item = _make_item(
            title="Smith blocks education bill HR-4521",
            summary="Senator Smith vetoed the education funding measure.",
        )
        score = _score(item, packet)
        assert score >= 0.45, f"Expected high score with marker, got {score}"


class TestSameActorWrongEvent:
    """Items about the same actor but a different event should score low."""

    def test_same_actor_different_action(self):
        """Same senator, different action → low score."""
        packet = _make_packet()
        item = _make_item(
            title="Senator Smith launches presidential campaign",
            summary="Smith announced a new presidential campaign today.",
        )
        score = _score(item, packet)
        assert score < 0.45, f"Expected low score for wrong event, got {score}"

    def test_same_actor_must_not_have_rejection(self):
        """Items with must-not-have terms should score zero."""
        packet = _make_packet()
        item = _make_item(
            title="Senator Smith vetoes healthcare reform bill",
            summary="The healthcare bill was blocked by Smith.",
        )
        score = _score(item, packet)
        assert score == 0.0, f"Expected 0 for must-not-have term, got {score}"


class TestSameTopicWrongDate:
    """Items about the same topic but outside the date window should be penalized."""

    def test_old_article_about_same_topic(self):
        """Article from months ago on same topic gets lower date overlap."""
        packet = _make_packet()
        old_date = datetime(2025, 1, 15, tzinfo=UTC)
        item = _make_item(
            title="Senator Smith vetoes education funding bill",
            summary="The bill HR-4521 was vetoed.",
            published=old_date,
        )
        score_old = _score(item, packet)

        recent_date = datetime(2026, 4, 17, tzinfo=UTC)
        item_recent = _make_item(
            title="Senator Smith vetoes education funding bill",
            summary="The bill HR-4521 was vetoed.",
            published=recent_date,
        )
        score_recent = _score(item_recent, packet)
        # Recent should score higher due to date overlap
        assert score_recent >= score_old


class TestSummaryOnlyMatch:
    """Headlines that don't match but summaries do get a penalty."""

    def test_summary_only_match_penalized(self):
        """Title mismatch with summary match gets penalty."""
        packet = _make_packet()
        item = _make_item(
            title="Breaking political news today",
            summary="Senator Smith vetoes education funding bill HR-4521.",
        )
        score = _score(item, packet)
        # Should have some score but penalized for summary-only match
        # The penalty is 0.18 per the implementation
        assert score < 0.60, f"Summary-only match should be penalized, got {score}"


class TestDistinctiveMarkerMatching:
    """Distinctive markers (numbers, quotes, platforms) improve matching."""

    def test_number_marker_overlap(self):
        """Number markers improve score."""
        packet = _make_packet()
        item_with_marker = _make_item(
            title="Bill HR-4521 faces veto",
            summary="Education funding legislation at risk.",
        )
        item_no_marker = _make_item(
            title="Education bill faces veto",
            summary="Funding legislation at risk.",
        )
        score_with = _score(item_with_marker, packet)
        score_without = _score(item_no_marker, packet)
        assert score_with > score_without


class TestMustNotHaveTerms:
    """must_not_have_terms should cause zero score."""

    def test_must_not_have_causes_zero(self):
        """Any must_not_have term in text → score is 0."""
        packet = _make_packet(must_not_have_terms=["immigration", "healthcare"])
        item = _make_item(
            title="Senator Smith vetoes immigration bill",
            summary="Smith blocked the immigration reform package.",
        )
        score = _score(item, packet)
        assert score == 0.0

    def test_no_must_not_have_allows_scoring(self):
        """Without must_not_have terms, scoring proceeds normally."""
        packet = _make_packet(must_not_have_terms=[])
        item = _make_item(
            title="Senator Smith vetoes education funding bill",
            summary="The bill was vetoed.",
        )
        score = _score(item, packet)
        assert score > 0.0
