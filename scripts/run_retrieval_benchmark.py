"""Run deterministic retrieval-quality checks over benchmark fixtures."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

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
    return "\n".join(lines) + "\n"


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
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit non-zero when any fixture has false positives, false negatives, or warnings.",
    )
    args = parser.parse_args()

    report = run_benchmarks(args.fixtures)
    output = (
        json.dumps(report, indent=2, sort_keys=True)
        if args.format == "json"
        else format_markdown(report)
    )
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    if args.fail_on_regression and report["aggregate"]["failed_fixture_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
