import json

from scripts.export_diagnostics_report import (
    aggregate_summaries,
    format_markdown,
    summarize_diagnostics,
)


def test_diagnostics_summary_tracks_runtime_rss_semantic_and_visual_metrics():
    diagnostics = {
        "story_id": "story-123456789",
        "analysis_id": "analysis-1",
        "analysis_run": {
            "status": "retrieval_complete",
            "started_at": "2026-05-02T10:00:00",
            "completed_at": "2026-05-02T10:00:03.500000",
        },
        "candidate_census": {
            "by_bucket": {"left_side": 1, "right_side": 1},
            "missing_buckets": ["center"],
        },
        "visual_evidence": {
            "records": [
                {"fallback_reason": ""},
                {"fallback_reason": "browser_capture_unavailable"},
            ],
            "limitations": ["metadata only"],
        },
        "report_validation_warnings": [
            "Missing source findings for: S2",
            "Report is missing evidence limitations banner.",
            "Empty or generic key framing for: S3",
        ],
        "retrieval_candidates": [
            {
                "stage": "rss",
                "state": "retained",
                "relevance_diagnostics": {"semantic_similarity": 0.82},
            },
            {
                "stage": "rss",
                "state": "relevance_rejected",
                "relevance_diagnostics": {},
            },
            {
                "stage": "open_web",
                "state": "retained",
                "relevance_diagnostics": {"semantic_chunk_similarity": 0.77},
            },
        ],
    }

    summary = summarize_diagnostics(diagnostics)

    assert summary["runtime_seconds"] == 3.5
    assert summary["candidate_count"] == 3
    assert summary["retained_count"] == 2
    assert summary["rss_accept_rate"] == 0.5
    assert summary["semantic_scored_count"] == 2
    assert summary["visual_fallback_rate"] == 0.5
    assert summary["warning_count"] == 3
    assert summary["report_validation_warnings"] == [
        "Missing source findings for: S2",
        "Report is missing evidence limitations banner.",
        "Empty or generic key framing for: S3",
    ]


def test_diagnostics_report_markdown_and_json_are_stable():
    stories = [
        {
            "story_id": "story-123456789",
            "analysis_id": "analysis-1",
            "status": "failed",
            "runtime_seconds": 2.0,
            "candidate_count": 4,
            "retained_count": 1,
            "rss_candidate_count": 2,
            "rss_retained_count": 1,
            "rss_accept_rate": 0.5,
            "semantic_scored_count": 1,
            "visual_record_count": 2,
            "visual_fallback_count": 1,
            "visual_fallback_rate": 0.5,
            "warning_count": 1,
            "report_validation_warnings": ["Missing source findings for: S2"],
            "missing_buckets": ["right_side"],
            "bucket_coverage": {"left_side": 1},
        }
    ]
    report = {
        "story_count": 1,
        "missing_story_ids": [],
        "aggregate": aggregate_summaries(stories),
        "stories": stories,
    }

    markdown = format_markdown(report)
    encoded = json.dumps(report)

    assert "# Diagnostics Benchmark Report" in markdown
    assert (
        "| story-12 | failed | 2.000s | 4 | 1/2 | 1 | 1/2 | 1 | right_side |"
        in markdown
    )
    assert '"rss_accept_rate": 0.5' in encoded
