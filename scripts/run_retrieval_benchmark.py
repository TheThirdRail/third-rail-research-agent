"""Run deterministic retrieval-quality checks over benchmark fixtures."""

from __future__ import annotations

import argparse
import html
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from scripts.export_diagnostics_report import (
    export_diagnostics,
)
from scripts.export_diagnostics_report import (
    format_markdown as format_diagnostics_markdown,
)
from src.schemas.story_packet import StoryPacket
from src.services.relevance_scorer_service import RelevanceScorerService

DEFAULT_FIXTURE_DIR = Path("tests/fixtures/benchmarks")
PASSING_RELEVANCE_SCORE = 0.20


@dataclass(frozen=True)
class BenchmarkResult:
    """One fixture's benchmark metrics."""

    name: str
    candidate_count: int
    expected_retained: int
    expected_rejected: int
    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int
    precision: float
    recall: float
    accuracy: float
    bucket_coverage: dict[str, int]
    warnings: list[str]

    @property
    def passed(self) -> bool:
        return not self.warnings and self.false_positive == 0 and self.false_negative == 0


@dataclass(frozen=True)
class LiveBenchmarkResult:
    """One opt-in live pipeline benchmark attempt."""

    name: str
    story_id: str | None
    status: str
    error: str | None


def load_fixtures(fixture_dir: Path) -> list[dict[str, Any]]:
    """Load all benchmark fixture JSON files from a directory."""
    fixtures = []
    for path in sorted(fixture_dir.glob("*.json")):
        with path.open(encoding="utf-8") as file:
            fixtures.append(json.load(file))
    return fixtures


def run_benchmarks(fixture_dir: Path = DEFAULT_FIXTURE_DIR) -> dict[str, Any]:
    """Run all benchmark fixtures and return serializable metrics."""
    results = [evaluate_fixture(fixture) for fixture in load_fixtures(fixture_dir)]
    aggregate = _aggregate(results)
    return {
        "fixture_dir": str(fixture_dir),
        "aggregate": aggregate,
        "results": [asdict(result) | {"passed": result.passed} for result in results],
    }


def run_combined_benchmark(
    fixture_dir: Path = DEFAULT_FIXTURE_DIR,
    diagnostics_story_ids: list[str] | None = None,
    live_run: bool = False,
    live_limit: int | None = None,
) -> dict[str, Any]:
    """Run deterministic fixtures and optionally include persisted diagnostics."""
    report: dict[str, Any] = {"fixtures": run_benchmarks(fixture_dir)}
    live_story_ids: list[str] = []
    if live_run:
        live_report = run_live_benchmark(fixture_dir, limit=live_limit)
        report["live"] = live_report
        live_story_ids = [
            result["story_id"]
            for result in live_report["results"]
            if result.get("story_id")
        ]

    all_diagnostics_ids = list(diagnostics_story_ids or []) + live_story_ids
    if all_diagnostics_ids:
        report["diagnostics"] = export_diagnostics(all_diagnostics_ids)
    return report


def load_baseline(path: Path) -> dict[str, Any]:
    """Load benchmark baseline thresholds from JSON."""
    if not path.exists():
        raise FileNotFoundError(f"Benchmark baseline file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def apply_baseline(report: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """Attach regression results for configured min/max metric thresholds."""
    regressions = evaluate_baseline(report, baseline)
    report["regressions"] = {
        "passed": not regressions,
        "failed_count": len(regressions),
        "failures": regressions,
    }
    return report


def evaluate_baseline(report: dict[str, Any], baseline: dict[str, Any]) -> list[dict[str, Any]]:
    """Compare report metrics against baseline thresholds."""
    thresholds = baseline.get("thresholds", baseline)
    failures: list[dict[str, Any]] = []
    for path, expected in (thresholds.get("minimums", {}) or {}).items():
        actual = _metric_path(report, path)
        if actual is None or float(actual) < float(expected):
            failures.append(
                {
                    "metric": path,
                    "rule": "minimum",
                    "expected": expected,
                    "actual": actual,
                }
            )
    for path, expected in (thresholds.get("maximums", {}) or {}).items():
        actual = _metric_path(report, path)
        if actual is None or float(actual) > float(expected):
            failures.append(
                {
                    "metric": path,
                    "rule": "maximum",
                    "expected": expected,
                    "actual": actual,
                }
            )
    return failures


def run_live_benchmark(
    fixture_dir: Path = DEFAULT_FIXTURE_DIR,
    limit: int | None = None,
) -> dict[str, Any]:
    """Run fixture seed stories through the live analysis pipeline.

    This is intentionally opt-in because it can call configured providers,
    web search, screenshot capture, and the configured database.
    """
    from src.services import AnalysisService

    fixtures = load_fixtures(fixture_dir)
    if limit is not None:
        fixtures = fixtures[: max(0, limit)]

    service = AnalysisService()
    results: list[LiveBenchmarkResult] = []
    for fixture in fixtures:
        seed = fixture.get("seed", {})
        description = seed.get("description") or fixture.get("description") or fixture["name"]
        url = seed.get("url")
        try:
            analysis_result = service.analyze(description=description, url=url)
            story_id = analysis_result.get("story_id")
            results.append(
                LiveBenchmarkResult(
                    name=str(fixture.get("name", "unknown")),
                    story_id=str(story_id) if story_id else None,
                    status="completed" if story_id else "missing_story_id",
                    error=None if story_id else "Analysis completed without a story_id.",
                )
            )
        except Exception as exc:
            results.append(
                LiveBenchmarkResult(
                    name=str(fixture.get("name", "unknown")),
                    story_id=None,
                    status="failed",
                    error=str(exc),
                )
            )

    serialized = [asdict(result) for result in results]
    return {
        "fixture_dir": str(fixture_dir),
        "attempted_count": len(serialized),
        "completed_count": sum(1 for result in serialized if result["story_id"]),
        "failed_count": sum(1 for result in serialized if result["status"] == "failed"),
        "results": serialized,
    }


def evaluate_fixture(fixture: dict[str, Any]) -> BenchmarkResult:
    """Evaluate one benchmark fixture using deterministic local scorers."""
    candidates = fixture.get("simulated_candidates", [])
    packet = _story_packet(fixture)
    scorer = RelevanceScorerService()
    warnings = _fixture_warnings(fixture)

    true_positive = 0
    true_negative = 0
    false_positive = 0
    false_negative = 0
    expected_retained = 0
    expected_rejected = 0

    for candidate in candidates:
        expected_state = candidate.get("expected_state")
        if expected_state not in {"retained", "relevance_rejected"}:
            continue

        result = scorer.score(
            candidate_title=candidate.get("title", ""),
            candidate_text=candidate.get("text_excerpt", ""),
            candidate_date=None,
            story_packet=packet,
        )
        predicted_retained = result.total >= PASSING_RELEVANCE_SCORE
        expected_is_retained = expected_state == "retained"

        if expected_is_retained:
            expected_retained += 1
            if predicted_retained:
                true_positive += 1
            else:
                false_negative += 1
        else:
            expected_rejected += 1
            if predicted_retained:
                false_positive += 1
            else:
                true_negative += 1

    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    accuracy = _ratio(true_positive + true_negative, expected_retained + expected_rejected)

    return BenchmarkResult(
        name=str(fixture.get("name", "unknown")),
        candidate_count=len(candidates),
        expected_retained=expected_retained,
        expected_rejected=expected_rejected,
        true_positive=true_positive,
        true_negative=true_negative,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=precision,
        recall=recall,
        accuracy=accuracy,
        bucket_coverage=_bucket_coverage(candidates),
        warnings=warnings,
    )


def format_markdown(report: dict[str, Any]) -> str:
    """Format benchmark metrics as a compact Markdown report."""
    if "fixtures" in report:
        return format_combined_markdown(report)

    aggregate = report["aggregate"]
    lines = [
        "# Retrieval Benchmark Report",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Fixtures | {aggregate['fixture_count']} |",
        f"| Candidates | {aggregate['candidate_count']} |",
        f"| Precision | {aggregate['precision']:.3f} |",
        f"| Recall | {aggregate['recall']:.3f} |",
        f"| Accuracy | {aggregate['accuracy']:.3f} |",
        f"| Failed Fixtures | {aggregate['failed_fixture_count']} |",
        "",
        "| Fixture | Precision | Recall | Accuracy | FP | FN | Warnings |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for result in report["results"]:
        warning_text = "; ".join(result["warnings"]) if result["warnings"] else ""
        row = dict(result)
        row["warnings"] = warning_text
        lines.append(
            "| {name} | {precision:.3f} | {recall:.3f} | {accuracy:.3f} | "
            "{false_positive} | {false_negative} | {warnings} |".format(
                **row,
            )
        )
    if report.get("regressions"):
        lines.extend(["", format_regression_markdown(report["regressions"]).rstrip()])
    return "\n".join(lines) + "\n"


def format_combined_markdown(report: dict[str, Any]) -> str:
    """Format fixture and persisted diagnostics metrics as one Markdown report."""
    sections = [format_markdown(report["fixtures"]).rstrip()]
    live = report.get("live")
    if live:
        sections.append(format_live_markdown(live).rstrip())
    diagnostics = report.get("diagnostics")
    if diagnostics:
        sections.append(format_diagnostics_markdown(diagnostics).rstrip())
    if report.get("regressions"):
        sections.append(format_regression_markdown(report["regressions"]).rstrip())
    return "\n\n".join(sections) + "\n"


def format_regression_markdown(report: dict[str, Any]) -> str:
    """Format baseline regression status."""
    lines = [
        "# Baseline Regression Status",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Passed | {report['passed']} |",
        f"| Failures | {report['failed_count']} |",
        "",
        "| Metric | Rule | Expected | Actual |",
        "|---|---|---:|---:|",
    ]
    for failure in report["failures"]:
        lines.append(
            "| {metric} | {rule} | {expected} | {actual} |".format(**failure)
        )
    return "\n".join(lines) + "\n"


def format_live_markdown(report: dict[str, Any]) -> str:
    """Format opt-in live pipeline benchmark attempts."""
    lines = [
        "# Live Pipeline Benchmark",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Attempted | {report['attempted_count']} |",
        f"| Completed | {report['completed_count']} |",
        f"| Failed | {report['failed_count']} |",
        "",
        "| Fixture | Status | Story ID | Error |",
        "|---|---|---|---|",
    ]
    for result in report["results"]:
        lines.append(
            "| {name} | {status} | {story_id} | {error} |".format(
                name=result["name"],
                status=result["status"],
                story_id=result.get("story_id") or "",
                error=result.get("error") or "",
            )
        )
    return "\n".join(lines) + "\n"


def format_html(report: dict[str, Any]) -> str:
    """Format benchmark metrics as a small standalone HTML dashboard."""
    fixture_report = report.get("fixtures", report)
    diagnostics = report.get("diagnostics") if "fixtures" in report else None
    live = report.get("live") if "fixtures" in report else None
    aggregate = fixture_report["aggregate"]
    fixture_rows = "\n".join(
        _html_row(
            [
                result["name"],
                f"{result['precision']:.3f}",
                f"{result['recall']:.3f}",
                f"{result['accuracy']:.3f}",
                result["false_positive"],
                result["false_negative"],
                "; ".join(result["warnings"]),
            ]
        )
        for result in fixture_report["results"]
    )
    diagnostics_section = (
        _format_diagnostics_html(diagnostics)
        if diagnostics
        else "<section><h2>Persisted Diagnostics</h2><p>No diagnostics story IDs were supplied.</p></section>"
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Retrieval Benchmark Dashboard</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; color: #1f2937; }}
    h1, h2 {{ color: #111827; }}
    .metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr)); gap: 0.75rem; }}
    .metric {{ border: 1px solid #d1d5db; border-radius: 6px; padding: 0.75rem; }}
    .metric span {{ display: block; color: #4b5563; font-size: 0.85rem; }}
    .metric strong {{ display: block; font-size: 1.35rem; margin-top: 0.25rem; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
    th, td {{ border: 1px solid #d1d5db; padding: 0.5rem; text-align: left; }}
    th {{ background: #f3f4f6; }}
    td.number, th.number {{ text-align: right; }}
  </style>
</head>
<body>
  <h1>Retrieval Benchmark Dashboard</h1>
  <section>
    <h2>Fixture Summary</h2>
    <div class="metric-grid">
      {_metric("Fixtures", aggregate["fixture_count"])}
      {_metric("Candidates", aggregate["candidate_count"])}
      {_metric("Precision", f"{aggregate['precision']:.3f}")}
      {_metric("Recall", f"{aggregate['recall']:.3f}")}
      {_metric("Accuracy", f"{aggregate['accuracy']:.3f}")}
      {_metric("Failed Fixtures", aggregate["failed_fixture_count"])}
    </div>
    <table>
      <thead>
        <tr><th>Fixture</th><th class="number">Precision</th><th class="number">Recall</th><th class="number">Accuracy</th><th class="number">FP</th><th class="number">FN</th><th>Warnings</th></tr>
      </thead>
      <tbody>
        {fixture_rows}
      </tbody>
    </table>
  </section>
  {_format_live_html(live) if live else ""}
  {diagnostics_section}
  {_format_regression_html(report.get("regressions")) if report.get("regressions") else ""}
</body>
</html>
"""


def _format_regression_html(report: dict[str, Any]) -> str:
    rows = "\n".join(
        _html_row(
            [
                failure["metric"],
                failure["rule"],
                failure["expected"],
                failure["actual"],
            ]
        )
        for failure in report["failures"]
    )
    return f"""<section>
    <h2>Baseline Regression Status</h2>
    <div class="metric-grid">
      {_metric("Passed", report["passed"])}
      {_metric("Failures", report["failed_count"])}
    </div>
    <table>
      <thead>
        <tr><th>Metric</th><th>Rule</th><th class="number">Expected</th><th class="number">Actual</th></tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
  </section>"""


def _format_live_html(report: dict[str, Any]) -> str:
    rows = "\n".join(
        _html_row(
            [
                result["name"],
                result["status"],
                result.get("story_id") or "",
                result.get("error") or "",
            ]
        )
        for result in report["results"]
    )
    return f"""<section>
    <h2>Live Pipeline</h2>
    <div class="metric-grid">
      {_metric("Attempted", report["attempted_count"])}
      {_metric("Completed", report["completed_count"])}
      {_metric("Failed", report["failed_count"])}
    </div>
    <table>
      <thead>
        <tr><th>Fixture</th><th>Status</th><th>Story ID</th><th>Error</th></tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
  </section>"""


def _format_diagnostics_html(report: dict[str, Any]) -> str:
    aggregate = report["aggregate"]
    story_rows = "\n".join(
        _html_row(
            [
                str(story.get("story_id", ""))[:8],
                story.get("status") or "",
                _format_runtime(story.get("runtime_seconds")),
                story["candidate_count"],
                f"{story['rss_retained_count']}/{story['rss_candidate_count']}",
                story["semantic_scored_count"],
                f"{story['visual_fallback_count']}/{story['visual_record_count']}",
                story["warning_count"],
                ", ".join(story["missing_buckets"]),
            ]
        )
        for story in report["stories"]
    )
    missing = ""
    if report["missing_story_ids"]:
        missing = (
            "<p>Missing story IDs: "
            + html.escape(", ".join(report["missing_story_ids"]))
            + "</p>"
        )
    return f"""<section>
    <h2>Persisted Diagnostics</h2>
    <div class="metric-grid">
      {_metric("Stories", report["story_count"])}
      {_metric("Candidates", aggregate["candidate_count"])}
      {_metric("Retained", aggregate["retained_count"])}
      {_metric("RSS Accept Rate", f"{aggregate['rss_accept_rate']:.3f}")}
      {_metric("Semantic Scored", aggregate["semantic_scored_count"])}
      {_metric("Visual Fallback Rate", f"{aggregate['visual_fallback_rate']:.3f}")}
      {_metric("Warnings", aggregate["warning_count"])}
      {_metric("Failed Stories", aggregate["failed_story_count"])}
    </div>
    <table>
      <thead>
        <tr><th>Story</th><th>Status</th><th class="number">Runtime</th><th class="number">Candidates</th><th class="number">RSS</th><th class="number">Semantic</th><th class="number">Visual Fallback</th><th class="number">Warnings</th><th>Missing Buckets</th></tr>
      </thead>
      <tbody>
        {story_rows}
      </tbody>
    </table>
    {missing}
  </section>"""


def _metric(label: str, value: object) -> str:
    return (
        '<div class="metric"><span>'
        + html.escape(str(label))
        + "</span><strong>"
        + html.escape(str(value))
        + "</strong></div>"
    )


def _html_row(values: list[object]) -> str:
    cells = []
    for index, value in enumerate(values):
        css_class = ' class="number"' if index and _looks_numeric(value) else ""
        cells.append(f"<td{css_class}>{html.escape(str(value))}</td>")
    return "<tr>" + "".join(cells) + "</tr>"


def _looks_numeric(value: object) -> bool:
    return isinstance(value, int | float) or "/" in str(value) or str(value).endswith("s")


def _format_runtime(value: float | None) -> str:
    return f"{value:.3f}s" if value is not None else ""


def _metric_path(report: dict[str, Any], path: str) -> object | None:
    value: object = report
    for part in path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return None
    return value


def _story_packet(fixture: dict[str, Any]) -> StoryPacket:
    overrides = fixture.get("story_packet_overrides", {})
    seed = fixture.get("seed", {})
    description = seed.get("description") or fixture.get("description") or fixture["name"]
    return StoryPacket(
        canonical_headline=str(description),
        actors=overrides.get("actors", []),
        primary_action=str(overrides.get("primary_action", "")),
        query_pack=overrides.get("query_pack", [str(description)]),
        must_have_terms=overrides.get("must_have_terms", []),
        must_not_have_terms=overrides.get("must_not_have_terms", []),
        number_markers=overrides.get("number_markers", []),
        platform_markers=overrides.get("platform_markers", []),
        visual_descriptors=overrides.get("visual_descriptors", []),
    )


def _fixture_warnings(fixture: dict[str, Any]) -> list[str]:
    warnings = []
    candidates = fixture.get("simulated_candidates", [])
    expectations = fixture.get("expectations", {})

    required_buckets = set(expectations.get("retained_must_include_buckets", []))
    if required_buckets:
        present = set(_bucket_coverage(candidates))
        missing = sorted(required_buckets - present)
        if missing:
            warnings.append(f"missing candidate buckets: {', '.join(missing)}")

    if "visual_evidence_records_min" in expectations and not fixture.get("media_pointers"):
        warnings.append("visual evidence fixture has no media pointers")

    return warnings


def _bucket_coverage(candidates: list[dict[str, Any]]) -> dict[str, int]:
    coverage = {"left_side": 0, "center": 0, "right_side": 0}
    for candidate in candidates:
        bias = int(candidate.get("bias", 0) or 0)
        if bias <= -1:
            coverage["left_side"] += 1
        elif bias >= 1:
            coverage["right_side"] += 1
        else:
            coverage["center"] += 1
    return {bucket: count for bucket, count in coverage.items() if count}


def _aggregate(results: list[BenchmarkResult]) -> dict[str, Any]:
    tp = sum(result.true_positive for result in results)
    tn = sum(result.true_negative for result in results)
    fp = sum(result.false_positive for result in results)
    fn = sum(result.false_negative for result in results)
    candidate_count = sum(result.candidate_count for result in results)
    return {
        "fixture_count": len(results),
        "candidate_count": candidate_count,
        "true_positive": tp,
        "true_negative": tn,
        "false_positive": fp,
        "false_negative": fn,
        "precision": _ratio(tp, tp + fp),
        "recall": _ratio(tp, tp + fn),
        "accuracy": _ratio(tp + tn, tp + tn + fp + fn),
        "failed_fixture_count": sum(0 if result.passed else 1 for result in results),
    }


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURE_DIR)
    parser.add_argument("--format", choices=["json", "markdown", "html"], default="markdown")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--diagnostics-story-id",
        action="append",
        default=[],
        help="Include persisted diagnostics metrics for a story ID. May be repeated.",
    )
    parser.add_argument(
        "--live-run",
        action="store_true",
        help=(
            "Run fixture seed stories through the configured live analysis pipeline. "
            "This may call external providers/search and write to the configured database."
        ),
    )
    parser.add_argument(
        "--live-limit",
        type=int,
        default=None,
        help="Maximum number of fixture seeds to run when --live-run is enabled.",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit non-zero when any fixture has false positives, false negatives, or warnings.",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="JSON file with minimums/maximums metric thresholds.",
    )
    args = parser.parse_args()

    report = (
        run_combined_benchmark(
            args.fixtures,
            args.diagnostics_story_id,
            live_run=args.live_run,
            live_limit=args.live_limit,
        )
        if args.diagnostics_story_id or args.live_run
        else run_benchmarks(args.fixtures)
    )
    if args.baseline:
        try:
            apply_baseline(report, load_baseline(args.baseline))
        except Exception as exc:
            print(f"Benchmark baseline error: {exc}")
            return 2
    if args.format == "json":
        output = json.dumps(report, indent=2, sort_keys=True)
    elif args.format == "html":
        output = format_html(report)
    else:
        output = format_markdown(report)
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    fixture_report = report.get("fixtures", report)
    diagnostics_report = report.get("diagnostics", {}) if "fixtures" in report else {}
    live_report = report.get("live", {}) if "fixtures" in report else {}
    if args.fail_on_regression and (
        fixture_report["aggregate"]["failed_fixture_count"]
        or diagnostics_report.get("missing_story_ids")
        or live_report.get("failed_count", 0)
        or report.get("regressions", {}).get("failed_count", 0)
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
