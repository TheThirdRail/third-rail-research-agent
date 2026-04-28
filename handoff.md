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

The following items remain on the integration checklist and are the primary focus for the next session.

### 1. Wire `BalancedSourcePlanner` into `SourceAggregatorService`
Currently, `gather_sources()` fetches results and appends them based on a greedy loop with simple threshold breaks (`retained_source_max`, `_bias_spread_met`).
**Task:**
- Initialize `BalancedSourcePlanner` inside `SourceAggregatorService`.
- Call `planner.plan(seed_bias)` to determine the `required_buckets` and `optional_buckets`.
- Instead of just checking if a bias spread is met loosely, use the planner's structured output to drive the discovery loop.
- Use the newly built `score_candidate` logic from `src/services/source_scoring.py` to rank candidate URLs based on bucket needs, duplicate penalties, factuality, and freshness, rather than just appending the first valid links found.

### 2. Wire `RelevanceScorerService` into `SourceAggregatorService`
Currently, candidate URLs are checked for text length and duplicates, but not deeply evaluated for story relevance.
**Task:**
- Inside the `gather_sources()` discovery loop (or as a batch processing step), initialize `RelevanceScorerService`.
- Use the `StoryPacket` (which is now generated at the beginning of `AnalysisService.analyze()`) to score candidates via `scorer.score()`.
- Reject candidates that fall below the relevance threshold (e.g., mismatching entities/events). 
- *Note:* You will need to pass the `StoryPacket` down from `AnalysisService.analyze()` into `SourceAggregatorService.gather_sources()`.

### 3. End-to-End Integration Testing
Once the above wiring is complete, the entire pipeline needs to be verified end-to-end.
**Task:**
- Create an integration test (e.g., `tests/test_end_to_end_analysis.py`).
- Provide a seed URL and description.
- Assert that the pipeline correctly parses the story, uses the planner to find diverse sources, filters out irrelevant hits via the relevance scorer, runs the crew, and produces a final `ReportRenderer` markdown string that contains the `Source Matrix` and deterministic footnotes.

### 4. Code Cleanup & Finalization
- Review the codebase for any remaining obsolete fallback logic (e.g., old YAML loading mechanisms that might have been missed).
- Review `model-lock-in.md` and decide on the timeline for finalizing the model selection (currently deferred).
