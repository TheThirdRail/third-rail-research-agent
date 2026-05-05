"""Sweep relevance weight configurations and report optimal settings.

Runs the benchmark fixture suite across multiple weight profiles to identify
configurations that maximize precision, recall, and accuracy simultaneously.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any

from scripts.run_retrieval_benchmark import (
    DEFAULT_FIXTURE_DIR,
    PASSING_RELEVANCE_SCORE,
    _story_packet,
    load_fixtures,
)
from src.schemas.story_packet import StoryPacket
from src.services.relevance_scorer_service import RelevanceScorerService


@dataclass
class WeightProfile:
    """A named set of relevance score weights."""

    name: str
    weights: dict[str, float]
    rejection_threshold: float = 0.35
    passing_score: float = PASSING_RELEVANCE_SCORE


# Pre-defined weight profiles for comparison
PROFILES: list[WeightProfile] = [
    WeightProfile(
        name="default_no_semantic",
        weights={
            "entity_overlap": 0.30,
            "event_overlap": 0.25,
            "time_overlap": 0.15,
            "place_overlap": 0.10,
            "topic_match": 0.10,
            "novelty": 0.10,
        },
    ),
    WeightProfile(
        name="entity_heavy",
        weights={
            "entity_overlap": 0.40,
            "event_overlap": 0.20,
            "time_overlap": 0.15,
            "place_overlap": 0.05,
            "topic_match": 0.10,
            "novelty": 0.10,
        },
    ),
    WeightProfile(
        name="event_heavy",
        weights={
            "entity_overlap": 0.20,
            "event_overlap": 0.35,
            "time_overlap": 0.15,
            "place_overlap": 0.10,
            "topic_match": 0.10,
            "novelty": 0.10,
        },
    ),
    WeightProfile(
        name="topic_heavy",
        weights={
            "entity_overlap": 0.25,
            "event_overlap": 0.20,
            "time_overlap": 0.10,
            "place_overlap": 0.05,
            "topic_match": 0.30,
            "novelty": 0.10,
        },
    ),
    WeightProfile(
        name="balanced_tight",
        weights={
            "entity_overlap": 0.25,
            "event_overlap": 0.25,
            "time_overlap": 0.15,
            "place_overlap": 0.10,
            "topic_match": 0.15,
            "novelty": 0.10,
        },
    ),
    WeightProfile(
        name="low_novelty",
        weights={
            "entity_overlap": 0.30,
            "event_overlap": 0.30,
            "time_overlap": 0.15,
            "place_overlap": 0.10,
            "topic_match": 0.10,
            "novelty": 0.05,
        },
    ),
]

# Threshold sweep values
THRESHOLD_SWEEP = [0.15, 0.18, 0.20, 0.22, 0.25, 0.28, 0.30, 0.35]


@dataclass
class SweepResult:
    """Results from one profile/threshold combination."""

    profile_name: str
    passing_score: float
    rejection_threshold: float
    precision: float
    recall: float
    accuracy: float
    f1: float
    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int


def score_with_weights(
    scorer: RelevanceScorerService,
    candidate_title: str,
    candidate_text: str,
    packet: StoryPacket,
    weights: dict[str, float],
) -> float:
    """Score a candidate using custom weights instead of the scorer's defaults."""
    result = scorer.score(
        candidate_title=candidate_title,
        candidate_text=candidate_text,
        candidate_date=None,
        story_packet=packet,
    )
    # Recompute total using custom weights (no-semantic mode)
    total = (
        result.entity_overlap * weights.get("entity_overlap", 0.0)
        + result.event_overlap * weights.get("event_overlap", 0.0)
        + result.time_overlap * weights.get("time_overlap", 0.0)
        + result.place_overlap * weights.get("place_overlap", 0.0)
        + result.topic_match * weights.get("topic_match", 0.0)
        + result.novelty * weights.get("novelty", 0.0)
    )
    return total


def run_sweep(
    fixture_dir: Path = DEFAULT_FIXTURE_DIR,
    profiles: list[WeightProfile] | None = None,
    thresholds: list[float] | None = None,
) -> list[SweepResult]:
    """Run all profile × threshold combinations and return sorted results."""
    if profiles is None:
        profiles = PROFILES
    if thresholds is None:
        thresholds = THRESHOLD_SWEEP

    fixtures = load_fixtures(fixture_dir)
    scorer = RelevanceScorerService()
    results: list[SweepResult] = []

    for profile in profiles:
        for threshold in thresholds:
            tp, tn, fp, fn = 0, 0, 0, 0

            for fixture in fixtures:
                candidates = fixture.get("simulated_candidates", [])
                packet = _story_packet(fixture)

                for candidate in candidates:
                    expected_state = candidate.get("expected_state")
                    if expected_state not in {"retained", "relevance_rejected"}:
                        continue

                    score = score_with_weights(
                        scorer,
                        candidate.get("title", ""),
                        candidate.get("text_excerpt", ""),
                        packet,
                        profile.weights,
                    )
                    predicted_retained = score >= threshold
                    expected_retained = expected_state == "retained"

                    if expected_retained and predicted_retained:
                        tp += 1
                    elif expected_retained and not predicted_retained:
                        fn += 1
                    elif not expected_retained and predicted_retained:
                        fp += 1
                    else:
                        tn += 1

            precision = _ratio(tp, tp + fp)
            recall = _ratio(tp, tp + fn)
            f1 = (
                round(2 * precision * recall / (precision + recall), 6)
                if (precision + recall) > 0
                else 0.0
            )
            accuracy = _ratio(tp + tn, tp + tn + fp + fn)

            results.append(
                SweepResult(
                    profile_name=profile.name,
                    passing_score=threshold,
                    rejection_threshold=profile.rejection_threshold,
                    precision=precision,
                    recall=recall,
                    accuracy=accuracy,
                    f1=f1,
                    true_positive=tp,
                    true_negative=tn,
                    false_positive=fp,
                    false_negative=fn,
                )
            )

    # Sort by F1 descending, then accuracy descending
    results.sort(key=lambda r: (-r.f1, -r.accuracy))
    return results


def format_sweep_markdown(results: list[SweepResult], top_n: int = 15) -> str:
    """Format sweep results as Markdown."""
    lines = [
        "# Relevance Weight Sweep Results",
        "",
        f"Evaluated {len(results)} profile × threshold combinations.",
        "",
        f"## Top {min(top_n, len(results))} Configurations (by F1 score)",
        "",
        "| Rank | Profile | Threshold | Precision | Recall | F1 | Accuracy | FP | FN |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, result in enumerate(results[:top_n], 1):
        lines.append(
            f"| {rank} | {result.profile_name} | {result.passing_score:.2f} | "
            f"{result.precision:.3f} | {result.recall:.3f} | {result.f1:.3f} | "
            f"{result.accuracy:.3f} | {result.false_positive} | {result.false_negative} |"
        )

    # Best per profile
    lines.extend(["", "## Best Threshold Per Profile", ""])
    seen_profiles: set[str] = set()
    for result in results:
        if result.profile_name not in seen_profiles:
            seen_profiles.add(result.profile_name)
            lines.append(
                f"- **{result.profile_name}**: threshold={result.passing_score:.2f}, "
                f"F1={result.f1:.3f}, precision={result.precision:.3f}, "
                f"recall={result.recall:.3f}"
            )

    return "\n".join(lines) + "\n"


def format_sweep_json(results: list[SweepResult]) -> str:
    """Format sweep results as JSON."""
    serialized = []
    for result in results:
        serialized.append({
            "profile_name": result.profile_name,
            "passing_score": result.passing_score,
            "rejection_threshold": result.rejection_threshold,
            "precision": result.precision,
            "recall": result.recall,
            "accuracy": result.accuracy,
            "f1": result.f1,
            "true_positive": result.true_positive,
            "true_negative": result.true_negative,
            "false_positive": result.false_positive,
            "false_negative": result.false_negative,
        })
    return json.dumps({"sweep_results": serialized}, indent=2, sort_keys=True)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURE_DIR)
    parser.add_argument(
        "--format", choices=["json", "markdown"], default="markdown"
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--top", type=int, default=15, help="Number of top results to display"
    )
    args = parser.parse_args()

    results = run_sweep(args.fixtures)

    if args.format == "json":
        output = format_sweep_json(results)
    else:
        output = format_sweep_markdown(results, top_n=args.top)

    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
