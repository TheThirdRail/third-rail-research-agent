# Research Agent Hardening — Handoff Document

**Date:** April 28, 2026

## Overview

We have made significant progress on hardening the Research Agent architecture. The deterministic pipeline services (`StoryParserService`, `RelevanceScorerService`, `ReportRenderer`, etc.) have all been created, fully tested, and mostly integrated. The database schemas have been updated, and a migration script was created and verified against a live database. We also added full unit test coverage for the new services (45/45 tests passing).

## Completed in the Last Session

1. **AnalysisService Wiring:** Inserted `StoryParserService` to extract deterministic query packets and wired `ReportRenderer` as the post-processor to generate the final markdown reports (including source matrices and footnotes).
2. **Database Migrations:** Created an idempotent SQLite migration script (`scripts/migrate_hardening_columns.py`) to add the new columns (`parsed_metadata`, `bias_provenance`, `structured_claims`, etc.) and verified it locally.
3. **Duplicate Detection:** Wired `check_duplicate` into `SourceAggregatorService.gather_sources()`.
4. **Unit Tests:** Created comprehensive tests for all new components in `tests/test_hardening_services.py` and updated legacy tests to reflect new threshold configurations. All tests pass successfully.
5. **Checklist Update:** Marked off the completed integration items in `checklist2.md`.

## What Needs to be Completed (Next Steps)

The integration checklist is now complete.

### Completed This Session

1. **Balanced Source Planner Wiring:** `SourceAggregatorService.gather_sources()` now creates a seed-aware `BalancedSourcePlanner` plan, searches curated bucket targets before broad open-web fallback, scores candidates with `score_candidate()`, and selects sources to fill missing required buckets.
2. **Relevance Scorer Wiring:** `AnalysisService.analyze()` passes the parsed `StoryPacket` into `gather_sources()`. The aggregator now uses `RelevanceScorerService` to reject wrong-entity/wrong-event candidates before final source selection.
3. **End-to-End Integration Test:** Added `tests/test_end_to_end_analysis.py`, covering seed URL analysis through story parsing, planned source aggregation, relevance filtering, deterministic report rendering, Source Matrix generation, and footnotes.
4. **Bias Resolution Cleanup:** Removed a recursive `BiasClassifier` → `BiasResolutionService` fallback path and made `BiasResolutionService` use the local registry lookup directly before AllSides/LLM/heuristic fallbacks.
5. **Serialization Fix:** Persisted `StoryPacket` metadata with `model_dump_json()` so parsed datetime windows serialize correctly.

### Verification

- `python -m pytest tests -q` → 152 passed.
- Touched-file Ruff check passed.
- Repo-wide Ruff check still reports older unrelated lint/style findings outside this change set.

### Remaining Deferred Item

- `model-lock-in.md` remains intentionally deferred; no runtime model decision was made in this pass.
