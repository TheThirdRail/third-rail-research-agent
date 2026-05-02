import json

from scripts.run_retrieval_benchmark import (
    DEFAULT_FIXTURE_DIR,
    format_markdown,
    run_benchmarks,
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
    assert "| Fixture | Precision | Recall | Accuracy | FP | FN | Warnings |" in markdown
    assert "recurring_event_recurring_actors" in markdown
