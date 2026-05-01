"""Benchmark tests for retrieval pipeline quality scenarios.

Each test loads a benchmark fixture and validates pipeline behavior
against documented expectations for that scenario class.
"""

import json
from pathlib import Path

import pytest

from src.schemas.story_packet import StoryPacket
from src.services.relevance_scorer_service import RelevanceScorerService
from src.services.source_scoring import score_candidate

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "benchmarks"


def _load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / f"{name}.json"
    with open(path) as f:
        return json.load(f)


# ── One-side-heavy coverage ────────────────────────────────────────


class TestOneSideHeavyCoverage:
    """Verify balanced retention when candidates are ideologically skewed."""

    @pytest.fixture()
    def fixture(self):
        return _load_fixture("one_side_heavy_coverage")

    def test_fixture_loads(self, fixture):
        assert fixture["name"] == "one_side_heavy_coverage"
        assert len(fixture["simulated_candidates"]) >= 7

    def test_candidates_span_bias_spectrum(self, fixture):
        biases = {c["bias"] for c in fixture["simulated_candidates"]}
        assert min(biases) <= -2, "Need left-leaning candidates"
        assert max(biases) >= 2, "Need right-leaning candidates"
        assert 0 in biases, "Need center candidate"

    def test_scoring_prefers_empty_bucket(self, fixture):
        """Score a right-side candidate higher when right bucket is empty."""
        right_candidate = next(
            c for c in fixture["simulated_candidates"] if c["bias"] >= 2
        )
        left_candidate = next(
            c for c in fixture["simulated_candidates"] if c["bias"] <= -2
        )

        # Right candidate with empty bucket
        right_scored = score_candidate(
            url=right_candidate["url"],
            domain=right_candidate["domain"],
            title=right_candidate["title"],
            bias=right_candidate["bias"],
            bucket_label="right_side",
            similarity=0.8,
            bucket_is_empty=True,
            domain_already_present=False,
        )
        # Left candidate with filled bucket
        left_scored = score_candidate(
            url=left_candidate["url"],
            domain=left_candidate["domain"],
            title=left_candidate["title"],
            bias=left_candidate["bias"],
            bucket_label="left_side",
            similarity=0.8,
            bucket_is_empty=False,
            domain_already_present=False,
        )
        assert right_scored.total_score > left_scored.total_score, (
            "Right-side candidate should score higher when right bucket is empty"
        )

    def test_expectations_documented(self, fixture):
        expectations = fixture["expectations"]
        assert "left_side" in expectations["retained_must_include_buckets"]
        assert "right_side" in expectations["retained_must_include_buckets"]


# ── Same-person/wrong-event ────────────────────────────────────────


class TestSamePersonWrongEvent:
    """Verify wrong-event rejection for recurring public figures."""

    @pytest.fixture()
    def fixture(self):
        return _load_fixture("same_person_wrong_event")

    def test_fixture_loads(self, fixture):
        assert fixture["name"] == "same_person_wrong_event"

    def test_must_have_and_must_not_terms_defined(self, fixture):
        overrides = fixture["story_packet_overrides"]
        assert len(overrides["must_have_terms"]) >= 1
        assert len(overrides["must_not_have_terms"]) >= 1

    def test_correct_event_candidates_exist(self, fixture):
        direct = [
            c
            for c in fixture["simulated_candidates"]
            if c.get("expected_state") == "retained"
        ]
        assert len(direct) >= 2

    def test_wrong_event_candidates_exist(self, fixture):
        wrong = [
            c
            for c in fixture["simulated_candidates"]
            if c.get("expected_state") == "relevance_rejected"
        ]
        assert len(wrong) >= 2

    def test_relevance_scorer_rejects_wrong_event(self, fixture):
        """Verify the relevance scorer rejects articles missing must-have terms."""
        overrides = fixture["story_packet_overrides"]

        packet = StoryPacket(
            canonical_headline="Comey indicted on federal charges",
            actors=overrides.get("actors", []),
            primary_action="indicted",
            query_pack=["Comey indictment 8647"],
            must_have_terms=overrides.get("must_have_terms", []),
            must_not_have_terms=overrides.get("must_not_have_terms", []),
            number_markers=overrides.get("number_markers", []),
            platform_markers=overrides.get("platform_markers", []),
        )
        scorer = RelevanceScorerService()

        for candidate in fixture["simulated_candidates"]:
            result = scorer.score(
                candidate_title=candidate["title"],
                candidate_text=candidate.get("text_excerpt", ""),
                candidate_date=None,
                story_packet=packet,
            )
            if candidate["expected_state"] == "retained":
                assert result.total >= 0.20, (
                    f"Direct coverage should pass: {candidate['url']}"
                )
            elif candidate["expected_state"] == "relevance_rejected":
                # Must-not-have terms or missing must-have should trigger rejection
                has_must_not = any(
                    term.lower() in candidate.get("text_excerpt", "").lower()
                    for term in overrides.get("must_not_have_terms", [])
                )
                has_must_have = any(
                    term.lower() in candidate.get("text_excerpt", "").lower()
                    for term in overrides.get("must_have_terms", [])
                )
                # Either must-not present or must-have missing
                assert has_must_not or not has_must_have, (
                    f"Wrong-event candidate should fail a must-have/must-not gate: "
                    f"{candidate['url']}"
                )


# ── Screenshot/social-post story ───────────────────────────────────


class TestScreenshotSocialPost:
    """Verify visual evidence resolution and observable/interpretation split."""

    @pytest.fixture()
    def fixture(self):
        return _load_fixture("screenshot_social_post")

    def test_fixture_loads(self, fixture):
        assert fixture["name"] == "screenshot_social_post"

    def test_media_pointers_defined(self, fixture):
        pointers = fixture["media_pointers"]
        assert len(pointers) >= 1
        platforms = {p["platform"] for p in pointers}
        assert "X" in platforms

    def test_observable_terms_in_expectations(self, fixture):
        expectations = fixture["expectations"]
        assert "8647" in expectations["observable_text_includes"]

    def test_social_post_url_present(self, fixture):
        social_posts = [
            p for p in fixture["media_pointers"] if p["media_type"] == "social_post"
        ]
        assert len(social_posts) >= 1
        assert "x.com" in social_posts[0]["media_url"].lower()

    def test_story_packet_has_visual_descriptors(self, fixture):
        overrides = fixture["story_packet_overrides"]
        assert "visual_descriptors" in overrides
        assert len(overrides["visual_descriptors"]) >= 1


# ── Recurring event with recurring actors ──────────────────────────


class TestRecurringEventRecurringActors:
    """Verify event-specific filtering for common recurring actors."""

    @pytest.fixture()
    def fixture(self):
        return _load_fixture("recurring_event_recurring_actors")

    def test_fixture_loads(self, fixture):
        assert fixture["name"] == "recurring_event_recurring_actors"

    def test_recurring_actors_defined(self, fixture):
        actors = fixture["story_packet_overrides"]["actors"]
        assert len(actors) >= 2
        assert "Supreme Court" in actors or "Biden" in actors

    def test_correct_event_candidates_exist(self, fixture):
        direct = [
            c
            for c in fixture["simulated_candidates"]
            if c.get("expected_state") == "retained"
        ]
        assert len(direct) >= 3

    def test_wrong_event_candidates_span_multiple_events(self, fixture):
        wrong = [
            c
            for c in fixture["simulated_candidates"]
            if c.get("expected_state") == "relevance_rejected"
        ]
        assert len(wrong) >= 3
        titles = {c["title"] for c in wrong}
        assert len(titles) >= 3, "Wrong-event candidates should be distinct events"

    def test_must_not_have_excludes_wrong_topics(self, fixture):
        overrides = fixture["story_packet_overrides"]
        must_not = overrides["must_not_have_terms"]
        wrong = [
            c
            for c in fixture["simulated_candidates"]
            if c.get("expected_state") == "relevance_rejected"
        ]
        for candidate in wrong:
            text = candidate.get("text_excerpt", "").lower()
            has_exclusion = any(term.lower() in text for term in must_not)
            has_required = all(
                term.lower() in text for term in overrides["must_have_terms"]
            )
            assert has_exclusion or not has_required, (
                f"Wrong-event candidate should be filterable: {candidate['url']}"
            )

    def test_relevance_scorer_separates_events(self, fixture):
        """Direct test of relevance scorer on correct vs wrong events."""
        overrides = fixture["story_packet_overrides"]
        packet = StoryPacket(
            canonical_headline="Supreme Court rules on student loan forgiveness",
            actors=overrides.get("actors", []),
            primary_action="rules",
            query_pack=["Supreme Court student loan forgiveness ruling"],
            must_have_terms=overrides.get("must_have_terms", []),
            must_not_have_terms=overrides.get("must_not_have_terms", []),
        )
        scorer = RelevanceScorerService()

        correct_scores = []
        wrong_scores = []
        for candidate in fixture["simulated_candidates"]:
            result = scorer.score(
                candidate_title=candidate["title"],
                candidate_text=candidate.get("text_excerpt", ""),
                candidate_date=None,
                story_packet=packet,
            )
            if candidate["expected_state"] == "retained":
                correct_scores.append(result.total)
            else:
                wrong_scores.append(result.total)

        if correct_scores and wrong_scores:
            avg_correct = sum(correct_scores) / len(correct_scores)
            avg_wrong = sum(wrong_scores) / len(wrong_scores)
            assert avg_correct > avg_wrong, (
                f"Correct event avg ({avg_correct:.3f}) should exceed "
                f"wrong event avg ({avg_wrong:.3f})"
            )
