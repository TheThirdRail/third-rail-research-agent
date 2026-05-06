"""Tests for analysis pipeline structured events."""

import logging

import pytest

from src.core import analysis_events
from src.schemas.retrieval_diagnostics import CandidateDecision


class _RecordCollector(logging.Handler):
    """Minimal handler that collects formatted log output."""

    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(self.format(record))

    @property
    def text(self) -> str:
        return "\n".join(self.messages)


@pytest.fixture()
def captured_events():
    """Yield a collector attached to the analysis.events logger.

    This avoids relying on ``caplog`` / root logger level which can be
    polluted by earlier test modules (alembic, sqlalchemy, etc.).
    """
    evt_logger = logging.getLogger("analysis.events")
    collector = _RecordCollector()
    evt_logger.addHandler(collector)
    old_level = evt_logger.level
    old_disabled = evt_logger.disabled
    evt_logger.disabled = False
    evt_logger.setLevel(logging.DEBUG)
    yield collector
    evt_logger.removeHandler(collector)
    evt_logger.setLevel(old_level)
    evt_logger.disabled = old_disabled


class TestRunEvents:
    """Tests for run_started and run_completed events."""

    def test_run_started_returns_monotonic(self, captured_events):
        start = analysis_events.run_started(
            story_id="abc",
            description="Test story",
            url="https://example.com",
        )
        assert isinstance(start, float)
        assert start > 0
        assert "analysis.run_started" in captured_events.text

    def test_run_completed_logs_elapsed(self, captured_events):
        import time

        start = time.monotonic()
        analysis_events.run_completed(
            story_id="abc",
            status="analyzed",
            start_time=start,
            source_count=3,
            warnings_count=1,
        )
        assert "analysis.run_completed" in captured_events.text
        assert "analyzed" in captured_events.text


class TestCandidateTotals:
    """Tests for candidate lifecycle count events."""

    def test_counts_match_decisions(self, captured_events):
        decisions = [
            CandidateDecision(url="https://a.com", state="retained"),
            CandidateDecision(
                url="https://b.com",
                state="relevance_rejected",
                rejection_reason="wrong_event",
            ),
            CandidateDecision(url="https://c.com", state="extraction_failed"),
            CandidateDecision(
                url="https://d.com",
                state="duplicate_rejected",
                rejection_reason="exact_url",
            ),
        ]
        analysis_events.candidate_totals(
            story_id="abc",
            candidate_decisions=decisions,
        )
        assert "analysis.candidate_discovered_total" in captured_events.text
        assert "analysis.candidate_extracted_total" in captured_events.text
        assert "analysis.candidate_rejected_total" in captured_events.text


class TestBucketFillRatio:
    """Tests for bucket fill ratio events."""

    def test_emits_bucket_info(self, captured_events):
        coverage = {
            "retained_count": 3,
            "probed_count": 10,
            "left_count": 1,
            "center_count": 1,
            "right_count": 1,
            "missing_buckets": [],
        }
        analysis_events.bucket_fill_ratio(story_id="abc", coverage=coverage)
        assert "analysis.bucket_fill_ratio" in captured_events.text

    def test_missing_bucket_flagged(self, captured_events):
        coverage = {
            "retained_count": 2,
            "probed_count": 8,
            "left_count": 1,
            "center_count": 1,
            "right_count": 0,
            "missing_buckets": ["right_side"],
        }
        analysis_events.bucket_fill_ratio(story_id="abc", coverage=coverage)
        assert "right_side" in captured_events.text


class TestBucketProbeStarted:
    """Tests for bucket probe started events."""

    def test_emits_with_query(self, captured_events):
        analysis_events.bucket_probe_started(
            story_id="abc",
            bucket_label="left_side",
            stage="rss",
            exact_bias=-2,
            query="Comey indictment",
            domains=["cnn.com"],
        )
        assert "analysis.bucket_probe_started" in captured_events.text
        assert "left_side" in captured_events.text


class TestRssPrecision:
    """Tests for RSS precision events."""

    def test_precision_calculation(self, captured_events):
        analysis_events.rss_precision_at_accept(
            story_id="abc",
            rss_candidates=10,
            rss_accepted=3,
        )
        assert "analysis.rss_precision_at_accept" in captured_events.text
        assert "0.3" in captured_events.text

    def test_zero_candidates(self, captured_events):
        analysis_events.rss_precision_at_accept(
            story_id="abc",
            rss_candidates=0,
            rss_accepted=0,
        )
        assert "analysis.rss_precision_at_accept" in captured_events.text


class TestSemanticMemoryChunks:
    """Tests for semantic memory chunk count events."""

    def test_emits_counts(self, captured_events):
        analysis_events.semantic_memory_chunks_total(
            story_id="abc",
            chunks=12,
            documents=4,
        )
        assert "analysis.semantic_memory_chunks_total" in captured_events.text


class TestSocialPostResolve:
    """Tests for social post resolve events."""

    def test_emits_both_events(self, captured_events):
        analysis_events.social_post_resolve_result(
            story_id="abc",
            total=3,
            success=2,
            fallback=1,
        )
        assert "analysis.social_post_resolve_success_total" in captured_events.text
        assert "analysis.visual_fallback_total" in captured_events.text


class TestSourceMatrixKeyFraming:
    """Tests for source matrix key framing events."""

    def test_emits_gap_count(self, captured_events):
        analysis_events.source_matrix_missing_key_framing(
            story_id="abc",
            total_sources=5,
            missing_count=2,
        )
        assert (
            "analysis.source_matrix_missing_key_framing_total" in captured_events.text
        )


class TestReportValidationWarnings:
    """Tests for report validation warning events."""

    def test_classifies_warning_types(self, captured_events):
        warnings = [
            "Orphaned footnote [S4] not in source list",
            "Evidence limitation: missing right_side coverage",
            "Missing bucket: right_side",
            "Source URL not in allowed list: https://x.com",
            "Unknown issue detected",
        ]
        analysis_events.report_validation_warnings(
            story_id="abc",
            warnings=warnings,
        )
        assert "analysis.report_validation_warning_total" in captured_events.text
        assert "orphaned_citation" in captured_events.text
        assert "evidence_limitation" in captured_events.text

    def test_empty_warnings(self, captured_events):
        analysis_events.report_validation_warnings(
            story_id="abc",
            warnings=[],
        )
        assert "analysis.report_validation_warning_total" in captured_events.text
