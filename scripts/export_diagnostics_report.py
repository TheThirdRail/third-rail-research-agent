"""Export persisted analysis diagnostics as benchmark-style metrics."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.services import AnalysisService


def export_diagnostics(story_ids: list[str]) -> dict[str, Any]:
    """Load persisted diagnostics for story IDs and summarize quality signals."""
    service = AnalysisService()
    stories: list[dict[str, Any]] = []
    missing_story_ids: list[str] = []
    for story_id in story_ids:
        diagnostics = service.get_diagnostics(story_id)
        if diagnostics is None:
            missing_story_ids.append(story_id)
            continue
        stories.append(summarize_diagnostics(diagnostics))
    return {
        "story_count": len(stories),
        "missing_story_ids": missing_story_ids,
        "aggregate": aggregate_summaries(stories),
        "stories": stories,
    }


def summarize_diagnostics(diagnostics: dict[str, Any]) -> dict[str, Any]:
    """Summarize one story's persisted diagnostics."""
    candidates = diagnostics.get("retrieval_candidates", []) or []
    visual = diagnostics.get("visual_evidence", {}) or {}
    records = visual.get("records", []) or []
    report_warnings = diagnostics.get("report_validation_warnings", []) or []
    run = diagnostics.get("analysis_run", {}) or {}
    census = diagnostics.get("candidate_census", {}) or {}
    missing_buckets = census.get("missing_buckets", []) or []
    rss_candidates = [
        candidate for candidate in candidates if candidate.get("stage") == "rss"
    ]
    semantic_scored = [
        candidate
        for candidate in candidates
        if _has_semantic_diagnostics(candidate.get("relevance_diagnostics", {}))
    ]
    visual_fallback_count = sum(
        1 for record in records if record.get("fallback_reason")
    )
    warning_count = len(report_warnings)
    runtime_seconds = _runtime_seconds(run.get("started_at"), run.get("completed_at"))

    return {
        "story_id": diagnostics.get("story_id"),
        "analysis_id": diagnostics.get("analysis_id"),
        "status": run.get("status"),
        "runtime_seconds": runtime_seconds,
        "candidate_count": len(candidates),
        "retained_count": _count_state(candidates, "retained"),
        "rss_candidate_count": len(rss_candidates),
        "rss_retained_count": _count_state(rss_candidates, "retained"),
        "rss_accept_rate": _ratio(
            _count_state(rss_candidates, "retained"), len(rss_candidates)
        ),
        "semantic_scored_count": len(semantic_scored),
        "visual_record_count": len(records),
        "visual_fallback_count": visual_fallback_count,
        "visual_fallback_rate": _ratio(visual_fallback_count, len(records)),
        "warning_count": warning_count,
        "report_validation_warnings": report_warnings,
        "missing_buckets": missing_buckets,
        "bucket_coverage": census.get("by_bucket", {}) or {},
    }


def aggregate_summaries(stories: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate summarized diagnostics across stories."""
    candidate_count = sum(story["candidate_count"] for story in stories)
    retained_count = sum(story["retained_count"] for story in stories)
    rss_candidate_count = sum(story["rss_candidate_count"] for story in stories)
    rss_retained_count = sum(story["rss_retained_count"] for story in stories)
    visual_record_count = sum(story["visual_record_count"] for story in stories)
    visual_fallback_count = sum(story["visual_fallback_count"] for story in stories)
    runtimes = [
        story["runtime_seconds"]
        for story in stories
        if story["runtime_seconds"] is not None
    ]
    return {
        "candidate_count": candidate_count,
        "retained_count": retained_count,
        "rss_candidate_count": rss_candidate_count,
        "rss_retained_count": rss_retained_count,
        "rss_accept_rate": _ratio(rss_retained_count, rss_candidate_count),
        "semantic_scored_count": sum(
            story["semantic_scored_count"] for story in stories
        ),
        "visual_record_count": visual_record_count,
        "visual_fallback_count": visual_fallback_count,
        "visual_fallback_rate": _ratio(visual_fallback_count, visual_record_count),
        "warning_count": sum(story["warning_count"] for story in stories),
        "failed_story_count": sum(
            1 for story in stories if story.get("status") == "failed"
        ),
        "average_runtime_seconds": round(sum(runtimes) / len(runtimes), 3)
        if runtimes
        else None,
    }


def format_markdown(report: dict[str, Any]) -> str:
    """Format diagnostics metrics as Markdown."""
    aggregate = report["aggregate"]
    lines = [
        "# Diagnostics Benchmark Report",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Stories | {report['story_count']} |",
        f"| Candidates | {aggregate['candidate_count']} |",
        f"| Retained | {aggregate['retained_count']} |",
        f"| RSS Accept Rate | {aggregate['rss_accept_rate']:.3f} |",
        f"| Semantic Scored Candidates | {aggregate['semantic_scored_count']} |",
        f"| Visual Fallback Rate | {aggregate['visual_fallback_rate']:.3f} |",
        f"| Warnings | {aggregate['warning_count']} |",
        f"| Failed Stories | {aggregate['failed_story_count']} |",
        "",
        "| Story | Status | Runtime | Candidates | RSS | Semantic | Visual Fallback | Warnings | Missing Buckets |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for story in report["stories"]:
        runtime = (
            f"{story['runtime_seconds']:.3f}s"
            if story["runtime_seconds"] is not None
            else ""
        )
        missing = ", ".join(story["missing_buckets"])
        row = {
            **story,
            "story_ref": str(story.get("story_id", ""))[:8],
            "status": story.get("status") or "",
            "runtime": runtime,
            "missing": missing,
        }
        lines.append(
            "| {story_ref} | {status} | {runtime} | {candidate_count} | "
            "{rss_retained_count}/{rss_candidate_count} | {semantic_scored_count} | "
            "{visual_fallback_count}/{visual_record_count} | {warning_count} | "
            "{missing} |".format(
                **row,
            )
        )
    if report["missing_story_ids"]:
        lines.extend(
            [
                "",
                "Missing story IDs: " + ", ".join(report["missing_story_ids"]),
            ]
        )
    return "\n".join(lines) + "\n"


def _has_semantic_diagnostics(diagnostics: dict[str, Any]) -> bool:
    return any(
        diagnostics.get(key) is not None
        for key in (
            "semantic_similarity",
            "semantic_chunk_similarity",
            "semantic_title_similarity",
            "semantic_lede_similarity",
        )
    )


def _runtime_seconds(started_at: str | None, completed_at: str | None) -> float | None:
    if not started_at or not completed_at:
        return None
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(completed_at)
    except ValueError:
        return None
    return round(max((end - start).total_seconds(), 0.0), 3)


def _count_state(candidates: list[dict[str, Any]], state: str) -> int:
    return sum(1 for candidate in candidates if candidate.get("state") == state)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("story_ids", nargs="+", help="Story IDs to export.")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    report = export_diagnostics(args.story_ids)
    output = (
        json.dumps(report, indent=2, sort_keys=True)
        if args.format == "json"
        else format_markdown(report)
    )
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 1 if report["missing_story_ids"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
