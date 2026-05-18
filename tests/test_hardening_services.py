"""Tests for hardening pipeline services.

Covers: SourceRegistry, BalancedSourcePlanner, StoryParserService,
DuplicateDetector, SourceScoring, ReportRenderer, RelevanceScorerService,
ReportValidator (new rules), and BiasClassifier registry routing.
"""

import json
from datetime import UTC, datetime

from src.schemas.claims import Claim, ClaimType, FactExtractionResult
from src.schemas.narrative import NarrativeResult
from src.schemas.story_packet import StoryPacket
from src.services.balanced_source_planner import BalancedSourcePlanner
from src.services.duplicate_detector import check_duplicate
from src.services.relevance_scorer_service import RelevanceScorerService
from src.services.report_renderer import ReportRenderer, ReportSections, SourceRecord
from src.services.report_validator import (
    validate_evidence_limits,
    validate_orphaned_citations,
)
from src.services.source_registry import get_source_registry
from src.services.source_scoring import score_candidate
from src.services.story_parser_service import StoryParserService

# ─────────────────────── Source Registry ───────────────────────


class TestSourceRegistry:
    """Tests for the canonical source registry."""

    def test_registry_loads(self) -> None:
        registry = get_source_registry()
        assert len(registry.entries) > 50

    def test_lookup_known_domain(self) -> None:
        registry = get_source_registry()
        entry = registry.lookup_domain("foxnews.com")
        assert entry is not None
        assert entry.bias == 3
        assert entry.bias_label == "Right"

    def test_lookup_with_www_prefix(self) -> None:
        registry = get_source_registry()
        entry = registry.lookup_domain("www.reuters.com")
        assert entry is not None
        assert entry.bias == 0

    def test_lookup_unknown_domain_returns_none(self) -> None:
        registry = get_source_registry()
        assert registry.lookup_domain("unknownsite.example.com") is None

    def test_get_by_bucket_group(self) -> None:
        registry = get_source_registry()
        left = registry.get_by_bucket_group("left_side")
        right = registry.get_by_bucket_group("right_side")
        center = registry.get_by_bucket_group("center_side")
        assert len(left) > 0
        assert len(right) > 0
        assert len(center) > 0

    def test_get_by_category(self) -> None:
        registry = get_source_registry()
        libertarian = registry.get_by_category("libertarian")
        assert len(libertarian) >= 4

    def test_get_all_rss_feeds(self) -> None:
        registry = get_source_registry()
        feeds = registry.get_all_rss_feeds()
        total = sum(len(v) for v in feeds.values())
        assert total > 40

    def test_search_alias_lookup(self) -> None:
        registry = get_source_registry()
        entry = registry.lookup_domain("foxnews.com")
        assert entry is not None
        assert "Fox News" in entry.search_aliases


# ─────────────────────── Balanced Source Planner ────────────────


class TestBalancedSourcePlanner:
    """Tests for deterministic bucket planning."""

    def test_far_left_seed_requires_left_and_right(self) -> None:
        planner = BalancedSourcePlanner()
        plan = planner.plan(seed_bias=-4)
        labels = [b.label for b in plan.required_buckets]
        assert "left_side" in labels
        assert "right_side" in labels

    def test_far_right_seed_requires_left_and_right(self) -> None:
        planner = BalancedSourcePlanner()
        plan = planner.plan(seed_bias=4)
        labels = [b.label for b in plan.required_buckets]
        assert "left_side" in labels
        assert "right_side" in labels

    def test_center_seed_requires_left_and_right_with_center_optional(self) -> None:
        planner = BalancedSourcePlanner()
        plan = planner.plan(seed_bias=0)
        labels = [b.label for b in plan.required_buckets]
        assert "left_side" in labels
        assert "right_side" in labels
        assert "center" not in labels
        assert "center" in [b.label for b in plan.optional_buckets]

    def test_libertarian_is_always_optional(self) -> None:
        planner = BalancedSourcePlanner()
        for bias in [-4, -2, 0, 2, 4]:
            plan = planner.plan(seed_bias=bias)
            opt_labels = [b.label for b in plan.optional_buckets]
            assert "libertarian" in opt_labels

    def test_plan_has_required_and_optional(self) -> None:
        planner = BalancedSourcePlanner()
        plan = planner.plan(seed_bias=0)
        assert len(plan.required_buckets) >= 2
        assert len(plan.optional_buckets) >= 1

    def test_coverage_satisfied_initially_false(self) -> None:
        planner = BalancedSourcePlanner()
        plan = planner.plan(seed_bias=0)
        assert not plan.coverage_satisfied

    def test_plan_carries_round_robin_probe_metadata(self) -> None:
        planner = BalancedSourcePlanner()
        plan = planner.plan(seed_bias=-2)

        assert plan.bucket_probe_sequence[0] == "right_side"
        assert plan.proceed_minimum_groups == plan.required_labels
        assert all(bucket.probe_quota > 0 for bucket in plan.required_buckets)
        assert all(bucket.result_quota > 0 for bucket in plan.required_buckets)

    def test_search_plan_splits_required_buckets_by_exact_bias_lane(self) -> None:
        planner = BalancedSourcePlanner()
        plan = planner.plan(seed_bias=0)

        right_rss_lanes = [
            step.get("exact_bias")
            for step in plan.search_plan
            if step.get("bucket") == "right_side" and step.get("phase") == "rss"
        ]
        left_site_lanes = [
            step.get("exact_bias")
            for step in plan.search_plan
            if step.get("bucket") == "left_side" and step.get("phase") == "site_search"
        ]

        assert right_rss_lanes[:2] == [2, 3]
        assert left_site_lanes[:2] == [-2, -3]


# ─────────────────────── Story Parser ──────────────────────────


class TestStoryParser:
    """Tests for deterministic story parsing."""

    def test_basic_parsing(self) -> None:
        parser = StoryParserService()
        packet = parser.parse("Biden signs executive order on AI safety")
        assert packet.canonical_headline == "Biden signs executive order on AI safety"
        assert len(packet.query_pack) >= 1

    def test_multi_word_entity_extraction(self) -> None:
        parser = StoryParserService()
        packet = parser.parse(
            "President Joe Biden signed executive order banning TikTok"
        )
        assert "President Joe Biden" in packet.actors

    def test_action_verb_extraction(self) -> None:
        parser = StoryParserService()
        packet = parser.parse("Senate passed the infrastructure bill today")
        assert "passed" in packet.action_verbs

    def test_url_slug_extraction(self) -> None:
        parser = StoryParserService()
        packet = parser.parse(
            "New bill passes",
            "https://apnews.com/article/congress-new-spending-bill",
        )
        assert len(packet.query_pack) >= 2

    def test_story_packet_model(self) -> None:
        packet = StoryPacket(
            canonical_headline="Test headline",
            actors=["Actor A"],
            action_verbs=["signed"],
            query_pack=["test query"],
        )
        assert packet.canonical_headline == "Test headline"
        data = packet.model_dump()
        assert "actors" in data


# ─────────────────────── Duplicate Detector ────────────────────


class TestDuplicateDetector:
    """Tests for duplicate and syndication detection."""

    def test_same_domain_detected(self) -> None:
        result = check_duplicate(
            "https://cnn.com/article-2",
            "Article Title",
            "Some article body text here.",
            "cnn.com",
            [
                {
                    "url": "https://cnn.com/article-1",
                    "title": "Different Title",
                    "body_text": "Different content.",
                    "domain": "cnn.com",
                }
            ],
        )
        assert result.is_duplicate
        assert result.reason == "same_domain"

    def test_unique_source_not_duplicate(self) -> None:
        result = check_duplicate(
            "https://foxnews.com/article",
            "Fox Article",
            "Fox article body text.",
            "foxnews.com",
            [
                {
                    "url": "https://cnn.com/article",
                    "title": "CNN Article",
                    "body_text": "CNN article body.",
                    "domain": "cnn.com",
                }
            ],
        )
        assert not result.is_duplicate

    def test_empty_existing_always_unique(self) -> None:
        result = check_duplicate(
            "https://example.com/a",
            "Title",
            "Body text.",
            "example.com",
            [],
        )
        assert not result.is_duplicate

    def test_exact_url_match(self) -> None:
        result = check_duplicate(
            "https://cnn.com/same-article",
            "Title",
            "Body.",
            "cnn.com",
            [
                {
                    "url": "https://cnn.com/same-article",
                    "title": "Title",
                    "body_text": "Body.",
                    "domain": "cnn.com",
                }
            ],
        )
        assert result.is_duplicate


# ─────────────────────── Source Scoring ─────────────────────────


class TestSourceScoring:
    """Tests for multi-factor candidate scoring."""

    def test_score_returns_scored_candidate(self) -> None:
        result = score_candidate(
            url="https://reuters.com/article",
            domain="reuters.com",
            title="Test Article",
            bias=0,
            bucket_label="center",
            bucket_is_empty=True,
        )
        assert result.total_score > 0.0

    def test_bucket_need_bonus(self) -> None:
        needed = score_candidate(
            url="https://a.com/1",
            domain="a.com",
            title="Article",
            bias=0,
            bucket_label="center",
            bucket_is_empty=True,
        )
        filled = score_candidate(
            url="https://b.com/1",
            domain="b.com",
            title="Article",
            bias=0,
            bucket_label="center",
            bucket_is_empty=False,
        )
        assert needed.total_score > filled.total_score

    def test_duplicate_penalty(self) -> None:
        result = score_candidate(
            url="https://a.com/1",
            domain="a.com",
            title="Article",
            bias=0,
            bucket_label="center",
            is_duplicate=True,
        )
        assert result.duplicate_penalty < 0

    def test_semantic_similarity_supplies_event_similarity(self) -> None:
        result = score_candidate(
            url="https://a.com/1",
            domain="a.com",
            title="Article",
            bias=0,
            bucket_label="center",
            similarity=0.2,
            semantic_similarity=0.9,
        )
        assert result.event_similarity == 0.9
        assert result.similarity_score == 0.225

    def test_freshness_normalizes_aware_published_date(self) -> None:
        result = score_candidate(
            url="https://a.com/1",
            domain="a.com",
            title="Article",
            bias=0,
            bucket_label="center",
            published_date=datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC),
            reference_date=datetime(2026, 5, 13, 8, 0, 0),
        )

        assert result.freshness_score > 0.0


# ─────────────────────── Report Renderer ───────────────────────


class TestReportRenderer:
    """Tests for deterministic report rendering."""

    def test_render_adds_evidence_limits(self) -> None:
        renderer = ReportRenderer()
        sections = ReportSections(executive_summary="Some analysis text.")
        report = renderer.render(
            sources=[],
            sections=sections,
            missing_buckets=["left_side"],
        )
        assert "evidence limitation" in report.lower() or "left_side" in report.lower()

    def test_render_no_limits_when_covered(self) -> None:
        renderer = ReportRenderer()
        sections = ReportSections(executive_summary="All sides covered.")
        report = renderer.render(
            sources=[],
            sections=sections,
            missing_buckets=[],
        )
        # Should not have evidence limitation banner
        assert "left_side" not in report.lower() or "evidence" not in report.lower()

    def test_render_includes_source_matrix(self) -> None:
        sources = [
            SourceRecord(
                source_id="S1",
                title="Reuters Article",
                domain="reuters.com",
                url="https://reuters.com/article",
                bias=0,
                bias_label="Center",
                confidence=1.0,
            ),
        ]
        sections = ReportSections(executive_summary="Content here.")
        renderer = ReportRenderer()
        report = renderer.render(
            sources=sources,
            sections=sections,
            missing_buckets=[],
        )
        assert "Source Matrix" in report
        assert "reuters.com" in report

    def test_render_source_matrix_uses_source_findings(self) -> None:
        sources = [
            SourceRecord(
                source_id="S1",
                title="Reuters Article",
                domain="reuters.com",
                url="https://reuters.com/article",
                bias=0,
                bias_label="Center",
                confidence=1.0,
                key_framing="Frames the update as a confirmed timeline.",
                notable_claim="Officials confirmed the vote date.",
            ),
        ]
        report = ReportRenderer().render(
            sources,
            ReportSections(executive_summary="Content here."),
            missing_buckets=[],
        )

        assert "Frames the update as a confirmed timeline." in report
        assert "Officials confirmed the vote date." in report

    def test_render_single_matrix_and_story_first_sections(self) -> None:
        sources = [
            SourceRecord(
                source_id="S1",
                title="Reuters Article",
                domain="reuters.com",
                url="https://reuters.com/article",
                bias=0,
                bias_label="Center",
                confidence=1.0,
            ),
        ]
        sections = ReportSections(
            executive_summary="Brief summary.",
            what_happened="The event happened.",
            directly_observable="The image shows visible text.",
            what_is_disputed="The meaning is disputed.",
            coverage_snapshot="left=1 center=1 right=1",
        )
        report = ReportRenderer().render(sources, sections, missing_buckets=[])

        assert report.count("## Source Matrix") == 1
        assert report.count("## All Sources & Citations") == 1
        assert report.count("## Executive Summary") == 1
        assert report.index("## What Happened") < report.index("## Source Matrix")
        assert report.index("## Coverage Snapshot") < report.index("## Source Matrix")


# ─────────────────────── Relevance Scorer ──────────────────────


class TestRelevanceScorer:
    """Tests for multi-factor relevance scoring."""

    def test_score_returns_valid_result(self) -> None:
        scorer = RelevanceScorerService()
        packet = StoryPacket(
            canonical_headline="Congress passes AI bill",
            actors=["Congress"],
            action_verbs=["passes"],
            query_pack=["Congress AI bill"],
        )
        result = scorer.score(
            candidate_title="Congress passes AI regulation bill",
            candidate_text="The US Congress passed a comprehensive AI regulation bill today",
            candidate_date=None,
            story_packet=packet,
        )
        assert 0.0 <= result.total <= 1.0

    def test_high_relevance_for_matching_content(self) -> None:
        scorer = RelevanceScorerService()
        packet = StoryPacket(
            canonical_headline="Biden signs executive order",
            actors=["President Biden"],
            action_verbs=["signs"],
            query_pack=["Biden executive order"],
        )
        result = scorer.score(
            candidate_title="Biden signs executive order on AI",
            candidate_text="President Biden signed a sweeping executive order on artificial intelligence",
            candidate_date=None,
            story_packet=packet,
        )
        assert result.total > 0.1

    def test_rejection_reason_is_optional(self) -> None:
        scorer = RelevanceScorerService()
        packet = StoryPacket(
            canonical_headline="Test topic",
            actors=[],
            action_verbs=[],
            query_pack=["test"],
        )
        result = scorer.score(
            candidate_title="Something related",
            candidate_text="Content about the test topic",
            candidate_date=None,
            story_packet=packet,
        )
        # rejection_reason can be None or a string
        assert result.rejection_reason is None or isinstance(
            result.rejection_reason, str
        )


# ─────────────────────── Report Validator (new rules) ──────────


class TestReportValidatorNewRules:
    """Tests for new validation rules."""

    def test_evidence_limits_warns_when_missing_buckets(self) -> None:
        warnings = validate_evidence_limits("# Report\nSome analysis.", ["left_side"])
        assert len(warnings) > 0
        assert "evidence limitation" in warnings[0].lower()

    def test_evidence_limits_ok_when_banner_present(self) -> None:
        report = "# Report\n\n> **Evidence Limitation**: left_side not represented."
        warnings = validate_evidence_limits(report, ["left_side"])
        assert len(warnings) == 0

    def test_evidence_limits_ok_when_no_missing(self) -> None:
        warnings = validate_evidence_limits("# Report\nAll covered.", [])
        assert len(warnings) == 0

    def test_orphaned_citations_detected(self) -> None:
        report = "Some claim[^1]. Another claim[^3].\n\n[^1]: Source A — https://a.com"
        warnings = validate_orphaned_citations(report)
        assert len(warnings) == 1
        assert "[^3]" in warnings[0]

    def test_no_orphaned_citations(self) -> None:
        report = "Claim[^1].\n\n[^1]: Source A — https://a.com"
        warnings = validate_orphaned_citations(report)
        assert len(warnings) == 0


# ─────────────────────── Bias Classifier Registry Routing ──────


class TestBiasClassifierRegistryRouting:
    """Tests for bias classifier routing through source registry."""

    def test_known_domain_uses_registry(self) -> None:
        from src.tools.bias_classifier import BiasClassifier

        classifier = BiasClassifier()
        result = classifier.classify("foxnews.com")
        assert result.bias == 3
        assert result.bias_label == "Right"
        assert result.method == "dataset"

    def test_center_source(self) -> None:
        from src.tools.bias_classifier import BiasClassifier

        classifier = BiasClassifier()
        result = classifier.classify("reuters.com")
        assert result.bias == 0
        assert result.bias_label == "Center"

    def test_left_source(self) -> None:
        from src.tools.bias_classifier import BiasClassifier

        classifier = BiasClassifier()
        result = classifier.classify("cnn.com")
        assert result.bias == -2
        assert result.bias_label == "Lean Left"

    def test_unknown_domain_returns_unknown(self) -> None:
        from src.tools.bias_classifier import BiasClassifier

        classifier = BiasClassifier()
        result = classifier.classify("totallyunknown12345.example.com")
        assert result.bias_label == "Unknown"
        assert result.confidence == 0.0


# ─────────────────────── Pydantic Schema Roundtrips ────────────


class TestSchemaRoundtrips:
    """Tests for Pydantic model serialization."""

    def test_story_packet_roundtrip(self) -> None:
        packet = StoryPacket(
            canonical_headline="Test",
            actors=["Actor"],
            action_verbs=["did"],
            query_pack=["q"],
            location="DC",
        )
        data = json.loads(packet.model_dump_json())
        restored = StoryPacket(**data)
        assert restored.canonical_headline == "Test"
        assert restored.location == "DC"

    def test_claim_roundtrip(self) -> None:
        claim = Claim(
            claim_id="C1",
            normalized_claim="The bill passed 51-49",
            claim_type=ClaimType.OBSERVED_FACT,
            source_ids=["S1", "S2"],
            confidence=0.9,
        )
        data = json.loads(claim.model_dump_json())
        restored = Claim(**data)
        assert restored.normalized_claim == "The bill passed 51-49"
        assert restored.claim_type == ClaimType.OBSERVED_FACT

    def test_fact_extraction_roundtrip(self) -> None:
        result = FactExtractionResult(
            claims=[
                Claim(
                    claim_id="C1",
                    normalized_claim="Bill passed",
                    claim_type=ClaimType.OBSERVED_FACT,
                    source_ids=["S1"],
                    confidence=0.95,
                )
            ],
            agreed_facts_summary="Bill passed.",
        )
        data = json.loads(result.model_dump_json())
        restored = FactExtractionResult(**data)
        assert len(restored.claims) == 1

    def test_narrative_result_roundtrip(self) -> None:
        narrative = NarrativeResult(
            mainstream_narrative="Main take.",
            alternative_narrative="Alt take.",
            profile_aware_creator_angles=["Angle 1"],
        )
        data = json.loads(narrative.model_dump_json())
        restored = NarrativeResult(**data)
        assert len(restored.profile_aware_creator_angles) == 1
