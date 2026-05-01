# Dev Branch Hardening Handoff

Date: 2026-05-01

## Branch State

The working tree already contained active uncommitted implementation and planning
changes before this pass. This handoff covers the RSS story matching work from
the previous pass plus the candidate lifecycle persistence work completed next.

## Completed In This Pass

- Added story-aware RSS retrieval via
  `RssRetrievalService.search_story(packet, bucket_spec, max_results)`.
- Scored RSS candidates against story identity using headline/title overlap,
  actor overlap, action-verb overlap, distinctive terms, date-window overlap,
  and marker overlap for quotes, numbers, and social platforms.
- Rejected RSS candidates containing `StoryPacket.must_not_have_terms`.
- Added `rss_candidate_min_story_score` / `RSS_CANDIDATE_MIN_STORY_SCORE`
  thresholding and a summary-only weak-match penalty.
- Kept the existing `search()` method as the compatibility wrapper for callers
  that only have a query string.
- Wired `SourceAggregatorService` to call `search_story()` for RSS plan steps
  whenever a `StoryPacket` and matching bucket spec are available.
- Updated the hardening action plan and checklist to mark P0 RSS matching done.
- Added retrieval diagnostic schemas:
  `CandidateDecision` and `CandidateCensus`.
- Added durable `analysis_runs` and `retrieval_candidates` SQLAlchemy models.
- Added CRUD helpers for analysis runs and retrieval candidate bulk inserts.
- Tracked terminal candidate lifecycle states during source preflight:
  extraction failed, relevance rejected, duplicate rejected, policy rejected,
  extracted, and retained.
- Captured stage, extraction diagnostics, relevance diagnostics, source score,
  bucket label, exact bias, and media diagnostics for candidate decisions.
- Persisted retrieval candidates and candidate census from `AnalysisService`.
- Stored coverage, candidate census, and visual evidence snapshots on
  `analyses`.
- Added end-to-end assertions that retrieval lifecycle rows are persisted.
- Added structured missing-bucket explanations to the candidate census, including
  per-state counts, rejection-reason counts, and probe-limit status.
- Split planned bucket searches into per-exact-bias lanes so each bucket probes
  preferred bias values in order instead of flattening all bucket domains.
- Added legacy SQLite schema-sync regression coverage for the diagnostic
  `analysis_runs` / `retrieval_candidates` tables and analysis snapshot columns.
- Applied planned bucket `result_quota` during retained selection, with explicit
  non-strict backfill still able to satisfy the retained-source minimum.
- Recorded seed URL extraction under `primary` candidate lifecycle rows for both
  successful retained primary sources and failed/blocked primary extraction.
- Added explicit StoryPacket marker families for aliases, negative clues,
  quote markers, number markers, and platform markers, and wired RSS marker
  overlap to the explicit fields.
- Added deterministic query families via `SemanticQueryExpansionService` and
  made source aggregation prefer lexical, semantic paraphrase, opposing-frame,
  and visual/social query order during bucket probing.
- Added typed `RelevanceDiagnostics`, persisted that diagnostics payload for
  candidate lifecycle rows, and tightened relevance gates so semantic similarity
  cannot override must-have failures, must-not-have exclusions, or missing
  distinctive markers.
- Added candidate semantic title/lede similarity diagnostics while preserving
  the existing aggregate `score_candidate()` API.
- Added durable `source_findings` and `visual_evidence_records` SQLAlchemy
  models.
- Added CRUD helpers for source finding and visual evidence bulk inserts.
- Persisted report-writer source findings and visual observations from
  `AnalysisService` after analysis rows are created.
- Linked persisted source findings and visual evidence records back to retained
  `sources` when source refs or source URLs match.
- Extended migration/end-to-end coverage to verify first-class source finding
  and visual evidence persistence.
- Added durable `agent_findings` and `agent_handoffs` SQLAlchemy models.
- Added CRUD helpers for agent finding bulk inserts and handoff creation.
- Persisted post-retrieval and pre-crew handoff bundles from `AnalysisService`.
- Persisted structured fact/rhetoric/narrative/coverage findings as
  first-class `agent_findings`, separate from semantic-memory documents.
- Persisted per-agent handoff bundles for fact, rhetoric, narrative, and report
  handoff stages.
- Extended retained `sources` rows with relevance score, source score, bucket
  label, exact bias, coverage type, extraction diagnostics, media pointers,
  relevance diagnostics, media diagnostics, and key framing.
- Wired `AnalysisService` to populate retained source diagnostics from
  `SourceCandidate` plus retained `CandidateDecision` rows.
- Added legacy schema-sync and end-to-end assertions for source diagnostic
  persistence.
- Added bucket-lane attempt diagnostics to `CandidateCensus`, including bucket,
  stage, query, exact bias, targeted domains, returned/new result counts, and
  exhaustion reasons such as `no_results`, `bucket_probe_quota_reached`, and
  `global_result_limit_reached`.
- Added semantic chunk similarity to candidate semantic scoring and persisted
  relevance diagnostics, plus explicit wrong-event rejection reasons such as
  `same_person_wrong_event`.
- Added structured social-post resolution and screenshot-capture fallback:
  canonical URL handling for major social platforms, public oEmbed attempts
  where available, OCR/provenance/fallback fields, and routing of `social_post`
  media pointers through visual evidence records without storing raw screenshots.
- Added read-only diagnostics and handoff retrieval endpoints:
  `GET /analysis/{story_id}/diagnostics` and
  `GET /analysis/{story_id}/handoff/{stage}`.

## Files Touched

- `.env.example`
- `src/core/config.py`
- `src/services/rss_retrieval_service.py`
- `src/services/source_aggregator_service.py`
- `src/schemas/retrieval_diagnostics.py`
- `src/database/models.py`
- `src/database/crud.py`
- `src/database/__init__.py`
- `src/database/session.py`
- `src/database/__init__.py`
- `tests/test_migration_free_tier.py`
- `tests/test_analysis_rss_retrieval.py`
- `tests/test_source_aggregator_service.py`
- `tests/test_end_to_end_analysis.py`
- `tests/test_source_aggregator_service.py`
- `dev-branch-hardening-checklist.md`
- `docs/dev-branch-hardening-action-plan.md`

## Verification

```powershell
python -m ruff check src/core/config.py src/services/rss_retrieval_service.py src/services/source_aggregator_service.py tests/test_analysis_rss_retrieval.py tests/test_source_aggregator_service.py
```

Result: all checks passed.

```powershell
python -m pytest tests/test_analysis_rss_retrieval.py tests/test_source_aggregator_service.py -q
```

Result: 12 tests passed.

```powershell
python -m ruff check src/schemas/retrieval_diagnostics.py src/database/models.py src/database/crud.py src/database/__init__.py src/database/session.py src/services/source_aggregator_service.py src/services/analysis_service.py tests/test_end_to_end_analysis.py
```

Result: all checks passed.

```powershell
python -m pytest tests/test_source_aggregator_service.py tests/test_end_to_end_analysis.py -q
```

Result: 9 tests passed.

```powershell
python -m ruff check src/schemas/retrieval_diagnostics.py src/services/source_aggregator_service.py tests/test_source_aggregator_service.py
python -m pytest tests/test_source_aggregator_service.py -q
```

Result: Ruff passed; 8 source-aggregator tests passed.

```powershell
python -m ruff check src/services/balanced_source_planner.py src/services/source_aggregator_service.py tests/test_hardening_services.py tests/test_source_aggregator_service.py
python -m pytest tests/test_hardening_services.py tests/test_source_aggregator_service.py -q
```

Result: Ruff passed; 59 hardening/source-aggregator tests passed.

```powershell
python -m ruff check tests/test_migration_free_tier.py
python -m pytest tests/test_migration_free_tier.py -q
```

Result: Ruff passed; 4 migration tests passed.

```powershell
python -m ruff check src/services/source_aggregator_service.py tests/test_source_aggregator_service.py
python -m pytest tests/test_source_aggregator_service.py -q
python -m pytest tests/test_hardening_services.py tests/test_source_aggregator_service.py -q
```

Result: Ruff passed; 10 source-aggregator tests passed; 60 hardening/source-aggregator tests passed.

```powershell
python -m ruff check src/services/source_aggregator_service.py tests/test_source_aggregator_service.py tests/test_end_to_end_analysis.py
python -m pytest tests/test_source_aggregator_service.py tests/test_end_to_end_analysis.py -q
```

Result: Ruff passed; 13 source-aggregator/end-to-end tests passed.

```powershell
python -m ruff check src/schemas/story_packet.py src/services/story_parser_service.py src/services/rss_retrieval_service.py tests/test_story_parser_and_relevance.py tests/test_analysis_rss_retrieval.py
python -m pytest tests/test_story_parser_and_relevance.py tests/test_analysis_rss_retrieval.py -q
```

Result: Ruff passed; 16 story-parser/RSS tests passed.

```powershell
python -m ruff check src/schemas/story_packet.py src/services/story_parser_service.py src/services/semantic_query_expansion_service.py src/services/source_aggregator_service.py src/services/__init__.py tests/test_story_parser_and_relevance.py tests/test_source_aggregator_service.py
python -m pytest tests/test_story_parser_and_relevance.py tests/test_source_aggregator_service.py -q
```

Result: Ruff passed; 24 story-parser/source-aggregator tests passed.

```powershell
python -m ruff check src/schemas/retrieval_diagnostics.py src/services/relevance_scorer_service.py src/services/source_aggregator_service.py tests/test_story_parser_and_relevance.py tests/test_source_aggregator_service.py tests/test_end_to_end_analysis.py
python -m pytest tests/test_story_parser_and_relevance.py tests/test_source_aggregator_service.py tests/test_end_to_end_analysis.py -q
```

Result: Ruff passed; 29 story-parser/source-aggregator/end-to-end tests passed.

```powershell
python -m ruff check src/services/candidate_semantic_scorer.py src/services/source_aggregator_service.py tests/test_source_aggregator_service.py tests/test_semantic_memory_service.py
python -m pytest tests/test_source_aggregator_service.py tests/test_semantic_memory_service.py -q
```

Result: Ruff passed; 23 source-aggregator/semantic-memory tests passed.

```powershell
python -m ruff check src/database/models.py src/database/crud.py src/database/__init__.py src/services/analysis_service.py tests/test_migration_free_tier.py tests/test_end_to_end_analysis.py
python -m pytest tests/test_migration_free_tier.py tests/test_end_to_end_analysis.py -q
```

Result: Ruff passed; 6 migration/end-to-end tests passed.

```powershell
python -m ruff format src/database/models.py src/database/crud.py src/database/__init__.py src/services/analysis_service.py tests/test_migration_free_tier.py tests/test_end_to_end_analysis.py
python -m ruff check src/database/models.py src/database/crud.py src/database/__init__.py src/services/analysis_service.py tests/test_migration_free_tier.py tests/test_end_to_end_analysis.py
python -m pytest tests/test_migration_free_tier.py tests/test_end_to_end_analysis.py -q
```

Result: Ruff format/check passed; 6 migration/end-to-end tests passed.

```powershell
python -m ruff format src/database/models.py src/database/crud.py src/database/session.py src/services/analysis_service.py tests/test_migration_free_tier.py tests/test_end_to_end_analysis.py
python -m ruff check src/database/models.py src/database/crud.py src/database/session.py src/services/analysis_service.py tests/test_migration_free_tier.py tests/test_end_to_end_analysis.py
python -m pytest tests/test_migration_free_tier.py tests/test_end_to_end_analysis.py -q
```

Result: Ruff format/check passed; 6 migration/end-to-end tests passed.

```powershell
python -m ruff check src/schemas/retrieval_diagnostics.py src/services/source_aggregator_service.py tests/test_source_aggregator_service.py
python -m pytest tests/test_source_aggregator_service.py -q
```

Result: Ruff passed; 13 source-aggregator tests passed.

```powershell
python -m ruff check src/schemas/retrieval_diagnostics.py src/services/candidate_semantic_scorer.py src/services/relevance_scorer_service.py src/services/source_aggregator_service.py tests/test_hybrid_relevance_scoring.py tests/test_source_aggregator_service.py tests/test_story_parser_and_relevance.py
python -m pytest tests/test_hybrid_relevance_scoring.py tests/test_source_aggregator_service.py tests/test_story_parser_and_relevance.py -q
```

Result: Ruff passed; 31 hybrid relevance/story-parser/source-aggregator tests passed.

```powershell
python -m ruff format src/schemas/retrieval_diagnostics.py src/services/candidate_semantic_scorer.py src/services/relevance_scorer_service.py src/services/source_aggregator_service.py tests/test_hybrid_relevance_scoring.py tests/test_source_aggregator_service.py
python -m pytest tests/test_hybrid_relevance_scoring.py tests/test_source_aggregator_service.py tests/test_story_parser_and_relevance.py tests/test_end_to_end_analysis.py -q
python -m ruff check src/schemas/retrieval_diagnostics.py src/services/candidate_semantic_scorer.py src/services/relevance_scorer_service.py src/services/source_aggregator_service.py tests/test_hybrid_relevance_scoring.py tests/test_source_aggregator_service.py tests/test_story_parser_and_relevance.py tests/test_end_to_end_analysis.py
```

Result: Ruff format/check passed; 33 hybrid relevance/source-aggregator/story-parser/end-to-end tests passed.

```powershell
python -m ruff check src/schemas/visual_evidence.py src/schemas/__init__.py src/services/social_post_resolver_service.py src/services/screenshot_capture_service.py src/services/visual_evidence_service.py src/services/__init__.py tests/test_visual_evidence_service.py tests/test_end_to_end_analysis.py tests/test_semantic_memory_service.py
python -m pytest tests/test_visual_evidence_service.py tests/test_end_to_end_analysis.py tests/test_semantic_memory_service.py -q
python -m pytest tests/test_visual_evidence_service.py -q
```

Result: Ruff passed; 19 visual-evidence/end-to-end/semantic-memory tests passed; 6 visual-evidence service tests passed after import formatting.

```powershell
python -m ruff check src/api/routes/analyze.py src/services/analysis_service.py tests/test_end_to_end_analysis.py
python -m pytest tests/test_end_to_end_analysis.py -q
```

Result: Ruff passed; 2 end-to-end analysis tests passed after adding diagnostics/handoff retrieval.

## Remaining Work

The remaining open areas are now mainly P1/P2: actual restricted browser
screenshot capture, observability counters/events, and benchmarking.

## Notes For Next Agent

- The RSS scoring threshold is intentionally conservative and configurable.
- `search_story()` currently returns only `SearchResult`; detailed RSS scoring
  diagnostics should be captured later by the candidate lifecycle persistence
  work instead of overloading the search result contract.
- The old query-token RSS path still exists for compatibility and for any caller
  without a parsed `StoryPacket`.
