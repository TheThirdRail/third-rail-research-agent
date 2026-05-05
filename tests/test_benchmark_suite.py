"""Tests for the benchmark harness and fixture evaluation."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.run_retrieval_benchmark import (
    BenchmarkResult,
    DEFAULT_FIXTURE_DIR,
    evaluate_fixture,
    format_markdown,
    load_fixtures,
    run_benchmarks,
)
from scripts.sweep_relevance_weights import PROFILES, run_sweep


FIXTURE_DIR = DEFAULT_FIXTURE_DIR


class TestBenchmarkFixtureLoading:
    """Verify fixture loading and validation."""

    def test_load_fixtures_returns_list(self):
        fixtures = load_fixtures(FIXTURE_DIR)
        assert isinstance(fixtures, list)
        assert len(fixtures) >= 8

    def test_all_fixtures_have_required_fields(self):
        for fixture in load_fixtures(FIXTURE_DIR):
            assert "name" in fixture, f"Fixture missing 'name': {fixture}"
            assert "seed" in fixture or "description" in fixture

    def test_fixtures_with_expected_state_have_text_excerpts(self):
        for fixture in load_fixtures(FIXTURE_DIR):
            for candidate in fixture.get("simulated_candidates", []):
                if candidate.get("expected_state") in {"retained", "relevance_rejected"}:
                    assert candidate.get("text_excerpt"), (
                        f"Fixture '{fixture['name']}' candidate '{candidate.get('title', '')}' "
                        f"has expected_state but no text_excerpt"
                    )


class TestBenchmarkEvaluation:
    """Verify benchmark evaluation produces correct metrics."""

    def test_all_fixtures_pass(self):
        report = run_benchmarks(FIXTURE_DIR)
        aggregate = report["aggregate"]
        assert aggregate["failed_fixture_count"] == 0, (
            f"Failed fixtures: {[r['name'] for r in report['results'] if not r['passed']]}"
        )

    def test_precision_at_or_above_baseline(self):
        report = run_benchmarks(FIXTURE_DIR)
        assert report["aggregate"]["precision"] >= 0.85

    def test_recall_at_or_above_baseline(self):
        report = run_benchmarks(FIXTURE_DIR)
        assert report["aggregate"]["recall"] >= 0.85

    def test_accuracy_at_or_above_baseline(self):
        report = run_benchmarks(FIXTURE_DIR)
        assert report["aggregate"]["accuracy"] >= 0.85

    def test_no_false_positives(self):
        report = run_benchmarks(FIXTURE_DIR)
        assert report["aggregate"]["false_positive"] == 0

    def test_rejection_reasons_tracked(self):
        report = run_benchmarks(FIXTURE_DIR)
        reasons = report["aggregate"].get("rejection_reasons", {})
        assert len(reasons) > 0, "No rejection reasons tracked"
        assert "contains_disambiguation_exclusion" in reasons

    def test_coverage_type_breakdown_tracked(self):
        report = run_benchmarks(FIXTURE_DIR)
        breakdown = report["aggregate"].get("coverage_type_breakdown", {})
        assert "direct" in breakdown
        assert breakdown["direct"] > 0

    def test_query_family_counts_tracked(self):
        report = run_benchmarks(FIXTURE_DIR)
        families = report["aggregate"].get("query_family_counts", {})
        assert "lexical" in families
        assert families["lexical"] > 0

    def test_visual_evidence_fixtures_counted(self):
        report = run_benchmarks(FIXTURE_DIR)
        assert report["aggregate"].get("visual_fixtures_count", 0) >= 1


class TestBenchmarkSpecificFixtures:
    """Verify individual fixture behavior."""

    @pytest.fixture
    def fixtures(self) -> list[dict]:
        return load_fixtures(FIXTURE_DIR)

    def _find_fixture(self, fixtures, name: str) -> dict:
        for f in fixtures:
            if f["name"] == name:
                return f
        pytest.skip(f"Fixture '{name}' not found")

    def test_same_person_wrong_event_rejects_old_articles(self, fixtures):
        fixture = self._find_fixture(fixtures, "same_person_wrong_event")
        result = evaluate_fixture(fixture)
        assert result.true_negative >= 2, "Should reject at least 2 wrong-event articles"
        assert result.true_positive >= 2, "Should retain at least 2 correct articles"

    def test_temporal_proximity_uses_must_not_have(self, fixtures):
        fixture = self._find_fixture(fixtures, "temporal_proximity_disambiguation")
        result = evaluate_fixture(fixture)
        assert result.passed
        assert "contains_disambiguation_exclusion" in result.rejection_reasons

    def test_geographic_filtering_uses_location_exclusions(self, fixtures):
        fixture = self._find_fixture(fixtures, "geographic_event_filtering")
        result = evaluate_fixture(fixture)
        assert result.passed
        assert result.true_negative >= 3

    def test_weak_topic_match_rejects_tangential(self, fixtures):
        fixture = self._find_fixture(fixtures, "weak_topic_match_rejection")
        result = evaluate_fixture(fixture)
        assert result.passed
        assert result.true_negative >= 3

    def test_recurring_event_uses_event_markers(self, fixtures):
        fixture = self._find_fixture(fixtures, "recurring_event_recurring_actors")
        result = evaluate_fixture(fixture)
        assert result.passed

    def test_opinion_articles_correctly_rejected(self, fixtures):
        fixture = self._find_fixture(fixtures, "opinion_vs_direct_reporting")
        result = evaluate_fixture(fixture)
        assert result.passed
        assert "opinion" in result.coverage_type_breakdown


class TestMarkdownFormatting:
    """Verify Markdown report generation."""

    def test_format_includes_rejection_reasons(self):
        report = run_benchmarks(FIXTURE_DIR)
        md = format_markdown(report)
        assert "## Rejection Reason Breakdown" in md
        assert "contains_disambiguation_exclusion" in md

    def test_format_includes_coverage_type(self):
        report = run_benchmarks(FIXTURE_DIR)
        md = format_markdown(report)
        assert "## Coverage Type Distribution" in md

    def test_format_includes_query_families(self):
        report = run_benchmarks(FIXTURE_DIR)
        md = format_markdown(report)
        assert "## Query Family Generation" in md
        assert "lexical" in md


class TestWeightSweep:
    """Verify weight sweep produces results."""

    def test_sweep_returns_results(self):
        results = run_sweep(FIXTURE_DIR, profiles=PROFILES[:2], thresholds=[0.20, 0.30])
        assert len(results) == 4  # 2 profiles × 2 thresholds

    def test_sweep_results_sorted_by_f1(self):
        results = run_sweep(FIXTURE_DIR, profiles=PROFILES[:2], thresholds=[0.20, 0.30])
        for i in range(len(results) - 1):
            assert results[i].f1 >= results[i + 1].f1

    def test_sweep_all_profiles_evaluated(self):
        results = run_sweep(FIXTURE_DIR, profiles=PROFILES, thresholds=[0.25])
        profile_names = {r.profile_name for r in results}
        assert len(profile_names) == len(PROFILES)
