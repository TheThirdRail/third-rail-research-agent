import json

from scripts import run_retrieval_benchmark
from scripts.run_retrieval_benchmark import (
    DEFAULT_FIXTURE_DIR,
    apply_baseline,
    evaluate_baseline,
    format_html,
    format_live_markdown,
    format_markdown,
    run_benchmarks,
    run_combined_benchmark,
    run_live_benchmark,
)


def test_retrieval_benchmark_runner_reports_aggregate_metrics():
    report = run_benchmarks(DEFAULT_FIXTURE_DIR)

    assert report["aggregate"]["fixture_count"] >= 4
    assert report["aggregate"]["candidate_count"] >= 20
    assert 0.0 <= report["aggregate"]["precision"] <= 1.0
    assert 0.0 <= report["aggregate"]["recall"] <= 1.0
    assert 0.0 <= report["aggregate"]["accuracy"] <= 1.0
    assert {result["name"] for result in report["results"]} >= {
        "one_side_heavy_coverage",
        "same_person_wrong_event",
        "screenshot_social_post",
        "recurring_event_recurring_actors",
    }


def test_retrieval_benchmark_runner_output_is_json_serializable():
    report = run_benchmarks(DEFAULT_FIXTURE_DIR)

    encoded = json.dumps(report)

    assert "aggregate" in encoded
    assert "same_person_wrong_event" in encoded


def test_retrieval_benchmark_runner_formats_markdown_summary():
    report = run_benchmarks(DEFAULT_FIXTURE_DIR)

    markdown = format_markdown(report)

    assert "# Retrieval Benchmark Report" in markdown
    assert (
        "| Fixture | Precision | Recall | Accuracy | FP | FN | Cov.Type Acc. |"
        in markdown
    )
    assert "recurring_event_recurring_actors" in markdown


def test_retrieval_benchmark_runner_formats_html_dashboard():
    report = run_benchmarks(DEFAULT_FIXTURE_DIR)

    dashboard = format_html(report)

    assert "<!doctype html>" in dashboard
    assert "Retrieval Benchmark Dashboard" in dashboard
    assert "Fixture Summary" in dashboard
    assert "Persisted Diagnostics" in dashboard
    assert "same_person_wrong_event" in dashboard


def test_combined_benchmark_includes_persisted_diagnostics(monkeypatch):
    def fake_export_diagnostics(story_ids: list[str]) -> dict:
        return {
            "story_count": len(story_ids),
            "missing_story_ids": [],
            "aggregate": {
                "candidate_count": 3,
                "retained_count": 1,
                "rss_candidate_count": 2,
                "rss_retained_count": 1,
                "rss_accept_rate": 0.5,
                "semantic_scored_count": 1,
                "visual_record_count": 1,
                "visual_fallback_count": 0,
                "visual_fallback_rate": 0.0,
                "warning_count": 0,
                "failed_story_count": 0,
                "average_runtime_seconds": 1.25,
            },
            "stories": [
                {
                    "story_id": "story-123456789",
                    "analysis_id": "analysis-1",
                    "status": "completed",
                    "runtime_seconds": 1.25,
                    "candidate_count": 3,
                    "retained_count": 1,
                    "rss_candidate_count": 2,
                    "rss_retained_count": 1,
                    "rss_accept_rate": 0.5,
                    "semantic_scored_count": 1,
                    "visual_record_count": 1,
                    "visual_fallback_count": 0,
                    "visual_fallback_rate": 0.0,
                    "warning_count": 0,
                    "missing_buckets": [],
                    "bucket_coverage": {"left_side": 1, "right_side": 1},
                }
            ],
        }

    monkeypatch.setattr(
        run_retrieval_benchmark,
        "export_diagnostics",
        fake_export_diagnostics,
    )

    report = run_combined_benchmark(DEFAULT_FIXTURE_DIR, ["story-123456789"])
    markdown = format_markdown(report)
    dashboard = format_html(report)
    encoded = json.dumps(report)

    assert "fixtures" in report
    assert "diagnostics" in report
    assert "# Retrieval Benchmark Report" in markdown
    assert "# Diagnostics Benchmark Report" in markdown
    assert "Persisted Diagnostics" in dashboard
    assert "story-12" in dashboard
    assert "RSS Accept Rate" in dashboard
    assert "story-12" in markdown
    assert '"diagnostics"' in encoded


def test_live_benchmark_runs_fixture_seeds_and_exports_diagnostics(monkeypatch):
    analyzed: list[tuple[str, str | None]] = []

    class FakeAnalysisService:
        def analyze(self, description: str, url: str | None = None) -> dict:
            analyzed.append((description, url))
            return {"story_id": f"story-{len(analyzed)}"}

    def fake_export_diagnostics(story_ids: list[str]) -> dict:
        return {
            "story_count": len(story_ids),
            "missing_story_ids": [],
            "aggregate": {
                "candidate_count": 0,
                "retained_count": 0,
                "rss_candidate_count": 0,
                "rss_retained_count": 0,
                "rss_accept_rate": 0.0,
                "semantic_scored_count": 0,
                "visual_record_count": 0,
                "visual_fallback_count": 0,
                "visual_fallback_rate": 0.0,
                "warning_count": 0,
                "failed_story_count": 0,
                "average_runtime_seconds": None,
            },
            "stories": [],
        }

    monkeypatch.setattr(
        "src.services.AnalysisService",
        lambda: FakeAnalysisService(),
    )
    monkeypatch.setattr(
        run_retrieval_benchmark,
        "export_diagnostics",
        fake_export_diagnostics,
    )

    live_report = run_live_benchmark(DEFAULT_FIXTURE_DIR, limit=2)
    combined = run_combined_benchmark(DEFAULT_FIXTURE_DIR, live_run=True, live_limit=2)
    markdown = format_markdown(combined)
    dashboard = format_html(combined)

    assert live_report["attempted_count"] == 2
    assert live_report["completed_count"] == 2
    assert live_report["failed_count"] == 0
    assert (
        analyzed[0][0]
        == "Magnitude 6.2 earthquake strikes central Italy near Perugia, multiple buildings collapsed"
    )
    assert combined["diagnostics"]["story_count"] == 2
    assert "# Live Pipeline Benchmark" in markdown
    assert "Live Pipeline" in dashboard


def test_live_benchmark_records_analysis_failures(monkeypatch):
    class FakeAnalysisService:
        def analyze(self, description: str, url: str | None = None) -> dict:
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        "src.services.AnalysisService",
        lambda: FakeAnalysisService(),
    )

    report = run_live_benchmark(DEFAULT_FIXTURE_DIR, limit=1)
    markdown = format_live_markdown(report)

    assert report["attempted_count"] == 1
    assert report["completed_count"] == 0
    assert report["failed_count"] == 1
    assert report["results"][0]["status"] == "failed"
    assert "provider unavailable" in markdown


def test_benchmark_baseline_reports_threshold_failures():
    report = {
        "fixtures": {
            "aggregate": {
                "precision": 0.4,
                "failed_fixture_count": 0,
            }
        },
        "diagnostics": {
            "aggregate": {
                "warning_count": 3,
            }
        },
    }
    baseline = {
        "minimums": {"fixtures.aggregate.precision": 0.5},
        "maximums": {"diagnostics.aggregate.warning_count": 1},
    }

    failures = evaluate_baseline(report, baseline)
    updated = apply_baseline(report, baseline)

    assert len(failures) == 2
    assert updated["regressions"]["failed_count"] == 2
    assert updated["regressions"]["passed"] is False


def test_combined_markdown_includes_baseline_status():
    report = run_combined_benchmark(DEFAULT_FIXTURE_DIR, live_run=False)
    apply_baseline(
        report,
        {"minimums": {"fixtures.aggregate.candidate_count": 1}},
    )

    markdown = format_markdown(report)

    assert "# Baseline Regression Status" in markdown
    assert "| Passed | True |" in markdown
