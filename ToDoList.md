# Third Rail Research Agent — Incomplete / Partially Implemented Work List

## Purpose

This document lists the remaining implementation work identified from the current `dev` branch review against the two attached planning / diagnosis documents.

The important takeaway is that the repo is no longer at the older “mostly not implemented” state. Many core pieces now exist, but several are still scaffolding, disabled by default, partial, or not fully wired into the target architecture.

Use this as a coding-agent implementation checklist.

---

# 2026-05-03 Implementation Update

The remaining non-LanceDB work has been implemented as operational hardening:

- Alembic remains explicit through `research-agent init`; `research-agent health --strict` now checks current database revision against Alembic head.
- OCR has a reproducible validation command: `research-agent validate-ocr --force --fixtures tests/fixtures/ocr`.
- Live full-pipeline benchmarking is exposed through `research-agent benchmark --live`, with optional baseline thresholds and `--fail-on-regression`.
- Semantic query expansion remains current-story only. It does not read or reuse previous queries, older query history, or cross-story query memory. LLM-generated phrases are sanitized against current story anchors and fail open to deterministic query families.

LanceDB production validation remains intentionally out of scope.

---

# Status Legend

- **Incomplete**: Not implemented in a functional way yet.
- **Partially implemented**: Code exists, but the feature is incomplete, disabled by default, missing real backend behavior, or not fully wired.
- **Mostly implemented but needs hardening**: Feature exists and is wired, but needs tests, validation, repair behavior, or configuration polish.

---

# Highest-Priority Remaining Work

## 1. Add a real vector-store backend for semantic memory

**Status:** Incomplete

### Current state

The repo has a `SemanticMemoryService`, semantic document/chunk models, and embedding-provider plumbing. However, semantic memory currently stops at SQL-backed document/chunk storage with fake vector IDs. There is no real external vector database adapter yet.

The current implementation is useful as a canonical SQL memory layer, but it is not the full semantic retrieval architecture from the plan.

### What needs to be implemented

- Add a real vector-store adapter layer.
- Prefer LanceDB as the default local-first backend.
- Keep Chroma or FAISS as possible later alternatives, but do not overcomplicate the first implementation.
- Store embeddings in the vector backend with SQL IDs as durable metadata.
- Keep SQL as the source of truth.
- Treat the vector DB as a rebuildable retrieval index, not the only place where important state lives.

### Suggested files / areas

- `src/services/semantic_memory_service.py`
- `src/core/embedding_provider.py`
- New: `src/services/vector_store_service.py`
- New: `src/services/lancedb_vector_store.py`
- `src/database/models.py`
- Config settings in `src/core/config.py`

### Acceptance criteria

- Retained source chunks are embedded and inserted into LanceDB.
- Each vector record includes SQL-linked metadata:
  - `story_id`
  - `analysis_id`
  - `semantic_document_id`
  - `semantic_chunk_id`
  - `source_id`
  - `source_ref`
  - `document_type`
  - `domain`
  - `bias_bucket`
  - `exact_bias`
- Semantic search retrieves relevant chunks through LanceDB instead of re-embedding every SQL chunk on demand.
- If LanceDB is unavailable and fail-open is enabled, the system falls back cleanly to SQL/lexical retrieval.
- If fail-open is disabled, vector-store errors are surfaced clearly.

---

## 2. Replace screenshot fallback with real restricted screenshot capture

**Status:** Incomplete

### Current state

`ScreenshotCaptureService` exists, but it does not actually capture screenshots. It returns a structured fallback with:

- `render_method="not_configured"`
- `success=False`
- `fallback_reason="browser_capture_unavailable"`

This means social-post visual evidence is not truly screenshot-backed yet.

### What needs to be implemented

- Add restricted Playwright-based screenshot capture.
- Capture public social-post pages when possible.
- Store screenshot artifacts in a safe local artifact path.
- Capture provenance metadata.
- Optionally add OCR later, but the screenshot capture itself should come first.

### Suggested files / areas

- `src/services/screenshot_capture_service.py`
- `src/services/visual_evidence_service.py`
- `src/services/social_post_resolver_service.py`
- `src/schemas/visual_evidence.py`
- Config settings in `src/core/config.py`
- Possibly new artifact path helpers under `src/core/` or `src/services/`

### Acceptance criteria

- For supported public post URLs, the service attempts browser rendering.
- Screenshot artifacts are saved under a predictable local directory, for example:
  - `data/artifacts/screenshots/<story_id>/...`
- `ScreenshotArtifact` includes:
  - `artifact_path`
  - `render_method`
  - `success`
  - `fallback_reason`
  - `provenance`
  - `captured_at`
- Failures degrade into the existing structured fallback instead of crashing the whole analysis.
- The visual evidence report clearly distinguishes:
  - screenshot-backed evidence
  - oEmbed metadata
  - article alt text / captions
  - fallback-only evidence

---

## 3. Add OCR / visual text extraction for screenshot artifacts

**Status:** Mostly implemented

### Current state

The schema has an `ocr_text` field, and the visual evidence pipeline can carry OCR text. Optional screenshot OCR is now wired through `pytesseract` behind `SCREENSHOT_OCR_ENABLED=false` by default.

### What is now implemented

- OCR runs over captured screenshot artifacts when OCR is enabled and available.
- OCR output remains separate from model interpretation.
- OCR text flows into `ScreenshotArtifact.ocr_text` and social-post `VisualEvidenceRecord.ocr_text`.
- OCR text is included in visual evidence context and semantic memory text.
- OCR failures are captured as provenance/limitations instead of crashing the whole analysis.
- `research-agent health` runs a tiny local image through `pytesseract` when screenshot OCR is enabled, so missing system Tesseract binaries are surfaced as health errors.

### Suggested implementation options

Start simple:

- Use a local OCR dependency only if it is reliable and easy to install.
- If OCR installation becomes a trap, make OCR optional and feature-flagged.
- The first version can simply support screenshot capture and leave OCR disabled by default.

### Suggested files / areas

- `src/services/screenshot_capture_service.py`
- `src/services/visual_evidence_service.py`
- `src/schemas/visual_evidence.py`
- `src/database/models.py`

### Acceptance criteria

- OCR text is captured when OCR is enabled and available. Complete.
- OCR failures are stored as limitations, not fatal pipeline errors. Complete.
- OCR text is included in `VisualEvidenceRecord.ocr_text`. Complete.
- OCR text appears in visual evidence semantic memory documents. Complete.

### Remaining work

- Production-validate OCR against a real local Tesseract installation and representative screenshots.

---

## 4. Complete social-post visual evidence resolution

**Status:** Mostly implemented

### Current state

`SocialPostResolverService` exists and can canonicalize common social URLs. It recognizes:

- X / Twitter
- Instagram
- Threads
- Facebook
- TikTok
- Truth Social

However, metadata retrieval is only meaningfully implemented for X and TikTok through oEmbed. Other platforms mostly fall back to canonical URL handling.

Also, because screenshot capture is not real yet, the social-post evidence flow remains metadata-heavy.

### What needs to be implemented

- Add platform-specific metadata handling where feasible.
- Add browser screenshot fallback for platforms without oEmbed.
- Make social-post evidence first-class in the report and semantic memory.
- Avoid pretending a fallback metadata-only record is full visual proof.

### Suggested files / areas

- `src/services/social_post_resolver_service.py`
- `src/services/screenshot_capture_service.py`
- `src/services/visual_evidence_service.py`
- `src/schemas/visual_evidence.py`
- `src/database/models.py`

### Acceptance criteria

- X/Twitter and TikTok continue to use oEmbed where available.
- Instagram, Threads, Facebook, and Truth Social produce useful canonical metadata plus screenshot attempts.
- Every social-post record clearly stores:
  - platform
  - original URL
  - resolved URL
  - resolution method
  - screenshot success/failure
  - fallback reason if applicable
- The report does not overclaim from weak social metadata.

---

## 5. Replace startup schema patching with real migrations

**Status:** Incomplete

### Current state

The repo includes Alembic as a dependency, but schema evolution is still handled largely through startup-time `ensure_hardening_schema()` column patching.

That is fine for quick local hardening, but the current schema now includes enough new tables and fields that real migrations are needed.

### What needs to be implemented

- Add proper Alembic migrations for:
  - retrieval candidates
  - analysis runs
  - semantic documents
  - semantic chunks
  - source findings
  - visual evidence records
  - agent findings
  - agent handoffs
  - new source metadata columns
  - new analysis JSON snapshot columns
- Keep startup patching only as a backwards-compatibility safety net, not the main migration path.

### Suggested files / areas

- `alembic.ini`
- `migrations/` or `alembic/`
- `src/database/session.py`
- `src/database/models.py`

### Acceptance criteria

- Fresh DB initializes cleanly from migrations.
- Existing SQLite DB can upgrade safely.
- Startup no longer needs to grow a giant list of manual `ALTER TABLE` patches for major schema changes.
- Migration tests cover old-to-new upgrade behavior.

---

## 6. Expose analysis feature options through the service/API layer

**Status:** Incomplete / not fully exposed

### Current state

`AnalysisService.analyze()` currently accepts only:

- `description`
- optional `url`

But the plan called for configurable analysis options such as semantic memory, visual resolution, vector backend, strictness, embedding model, and retrieval behavior.

Most of those are only global config/environment settings right now.

### What needs to be implemented

Add an options object for analysis requests.

Example options:

```json
{
  "strict_bucket_enforcement": true,
  "required_bucket_groups": ["left_side", "right_side"],
  "preferred_bucket_groups": ["center"],
  "enable_semantic_memory": true,
  "enable_semantic_candidate_scoring": true,
  "enable_semantic_query_expansion": true,
  "enable_visual_evidence_resolution": true,
  "enable_screenshot_capture": true,
  "embedding_provider": "lmstudio",
  "embedding_model": "qwen3-embedding-8b",
  "vector_store": "lancedb"
}
```

### Suggested files / areas

- `src/services/analysis_service.py`
- API route files, if present
- Request/response schemas
- `src/core/config.py`

### Acceptance criteria

- CLI/API callers can override important analysis behavior per run.
- Defaults still work without passing options.
- Options are persisted into `analysis_runs` or an equivalent run config snapshot.
- Diagnostics show which options were used for a run.

---

## 7. Stop flattening query families too aggressively

**Status:** Partially implemented

### Current state

The repo now has query families:

- `lexical`
- `semantic_paraphrase`
- `opposing_frame`
- `visual_social`

However, `SourceAggregatorService._build_queries()` flattens them and truncates the final query list to four.

That weakens the intended “lane × query family” design. Important opposing-frame or visual/social queries can be dropped before bucket probing even begins.

### What needs to be implemented

- Preserve query families through the bucket scheduler.
- Search by bucket lane and query family instead of flattening everything too early.
- Allow different query families to be used for different retrieval phases.

Example:

- RSS phase: use lexical and canonical headline queries first.
- Site search phase: use lexical + distinctive marker queries.
- Open-web phase: use semantic paraphrase + opposing frame queries.
- Visual/social phase: use number markers, quote markers, platform markers, and visual descriptors.

### Suggested files / areas

- `src/services/source_aggregator_service.py`
- `src/services/semantic_query_expansion_service.py`
- `src/services/balanced_source_planner.py`
- `src/schemas/story_packet.py`

### Acceptance criteria

- Query families are not reduced to only four strings before retrieval.
- Bucket-lane attempts record the query family used.
- Diagnostics can show which family found or failed to find sources.
- Opposing-frame and visual/social queries get real attempts.

---

## 8. Make semantic query expansion meaning-aware, not just deterministic phrases

**Status:** Partially implemented

### Current state

`SemanticQueryExpansionService` exists, but it mostly builds deterministic phrase variants. `StoryParserService` has optional LLM expansion, but it is disabled by default.

There is no vector-memory-assisted query expansion yet.

### What needs to be implemented

- Use semantic memory to retrieve similar past headlines, story chunks, or agent findings.
- Generate better paraphrase queries from retrieved examples.
- Keep deterministic fallbacks for reliability.
- Keep LLM expansion JSON-only and fail-open.

### Suggested files / areas

- `src/services/semantic_query_expansion_service.py`
- `src/services/story_parser_service.py`
- `src/services/semantic_memory_service.py`
- `src/core/config.py`

### Acceptance criteria

- Deterministic expansion still works with no LLM or vector DB.
- LLM expansion can be enabled per run or config.
- Semantic memory can improve query expansion when available.
- Generated queries are short, search-friendly, and grouped by family.
- Bad LLM output does not crash analysis.

---

## 9. Make hybrid semantic relevance fully functional by default when configured

**Status:** Partially implemented

### Current state

`CandidateSemanticScorer` exists and can score candidate articles using embeddings. `SourceAggregatorService` can pass semantic scores into relevance scoring.

However:

- semantic candidate scoring is disabled by default
- default embedding provider is fake
- no vector-store-backed retrieval is implemented
- semantic behavior depends heavily on configuration

### What needs to be implemented

- Make real semantic scoring reliable with LM Studio.
- Add configuration validation so users know when semantic scoring is enabled but misconfigured.
- Store semantic score breakdowns consistently in retrieval diagnostics.
- Add tests with fake embeddings and integration tests with provider mocking.

### Suggested files / areas

- `src/services/candidate_semantic_scorer.py`
- `src/services/relevance_scorer_service.py`
- `src/services/source_aggregator_service.py`
- `src/core/embedding_provider.py`
- `src/core/config.py`

### Acceptance criteria

- When semantic candidate scoring is enabled, candidates store:
  - aggregate semantic similarity
  - title similarity
  - lede similarity
  - chunk similarity
- Relevance diagnostics include semantic values.
- Fail-open behavior works when configured.
- Fail-closed behavior works when configured.
- Semantic scoring materially affects source ranking when real embeddings are enabled.

---

## 10. Improve Source Matrix repair behavior

**Status:** Mostly implemented but needs hardening

### Current state

The repo now has:

- `SourceFinding` schema
- report-writer instructions requiring one finding per source
- `ReportRenderer` support for `key_framing` and `notable_claim`
- persistence into `source_findings`
- source-level `key_framing` updates
- event tracking for missing key framing

However, if the report writer fails to return complete `source_findings`, the Source Matrix still renders `—` instead of forcing a repair step.

### What needs to be implemented

- Add a deterministic fallback key-framing generator.
- Or add a structured repair pass when source findings are missing.
- Validate one `source_findings` entry per retained source before final render.

### Suggested files / areas

- `src/services/analysis_service.py`
- `src/schemas/analysis_report_sections.py`
- `src/services/report_validator.py`
- `src/services/report_renderer.py`
- Possibly new: `src/services/source_finding_service.py`

### Acceptance criteria

- Final Source Matrix never silently ships empty key-framing cells unless there is a clear limitation note.
- Missing `source_findings` triggers either:
  - deterministic fallback from title/excerpt, or
  - a JSON-only repair call, or
  - a clear validation warning and evidence limitation
- Tests cover missing, partial, malformed, and complete source findings.

---

## 11. Add stronger report validation around source findings

**Status:** Partially implemented

### Current state

The report system validates sources and structured payloads, and it rejects Markdown-shaped crew payloads. But the source-finding contract still needs stricter validation.

### What needs to be implemented

- Validate that every retained source has a source finding.
- Validate that source IDs match known `S1`, `S2`, etc.
- Validate that key framing is concise and not just generic filler.
- Validate that claims in source findings do not cite nonexistent source IDs.

### Suggested files / areas

- `src/services/report_validator.py`
- `src/schemas/analysis_report_sections.py`
- `src/services/analysis_service.py`

### Acceptance criteria

- Invalid source IDs are caught.
- Missing source findings are caught.
- Duplicate source findings are caught.
- Empty key framing is caught or repaired.

---

## 12. Add real migration and schema tests

**Status:** Incomplete

### Current state

No evidence was found that the specific migration tests from the plan exist.

### What needs to be implemented

Add tests for:

- fresh DB initialization
- old DB upgrade
- semantic memory tables
- retrieval candidate tables
- visual evidence tables
- source finding tables
- agent handoff tables
- backwards compatibility with existing SQLite files

### Suggested test files

- `tests/test_sql_migration_semantic_memory.py`
- `tests/test_database_schema_upgrade.py`
- `tests/test_retrieval_candidate_persistence.py`
- `tests/test_visual_evidence_persistence.py`
- `tests/test_source_findings_persistence.py`

### Acceptance criteria

- Tests can initialize a clean DB.
- Tests can simulate an older DB and upgrade it.
- All new tables and columns exist after migration.
- Existing records survive migration.

---

## 13. Add bucket fairness and retrieval scheduler tests

**Status:** Incomplete / not confirmed

### Current state

The bucket scheduler exists, but I did not find clear evidence of the full test suite required by the plan.

### What needs to be implemented

Add tests proving the system does not return “five of one side and stop.”

### Suggested test files

- `tests/test_bucket_round_robin_probe_scheduler.py`
- `tests/test_bucket_probe_quotas.py`
- `tests/test_exact_bias_caps.py`
- `tests/test_strict_bucket_enforcement.py`

### Test scenarios

- Seed is left-leaning, opposing-side lanes are probed first.
- Seed is right-leaning, opposing-side lanes are probed first.
- Center is preferred but not required by default.
- Required left/right buckets must be filled.
- Same exact-bias duplicates are capped.
- Same-bias backfill does not happen unless configured.
- Candidate probe limits do not starve required buckets unfairly.

### Acceptance criteria

- Round-robin behavior is deterministic.
- Missing bucket diagnostics explain what happened.
- Tests prove required buckets receive actual probe attempts.

---

## 14. Add RSS story-matching precision tests

**Status:** Incomplete / not confirmed

### Current state

`RssRetrievalService.search_story()` exists and scores RSS items against `StoryPacket`, but it needs regression tests for false positives and same-topic/wrong-event cases.

### What needs to be implemented

Add tests for:

- same actor, wrong event
- same topic, wrong date
- matching headline, weak summary-only match
- distinctive number/quote/platform marker matches
- must-not-have term rejection
- per-bucket RSS feed limits

### Suggested test files

- `tests/test_rss_story_matching_precision.py`
- `tests/test_rss_must_not_have_terms.py`
- `tests/test_rss_marker_overlap.py`

### Acceptance criteria

- RSS does not accept weak “same general topic” results.
- RSS accepts high-confidence same-story items.
- RSS diagnostics make failures explainable.

---

## 15. Add semantic memory and embedding tests

**Status:** Incomplete / not confirmed

### Current state

Semantic memory code exists, but the plan’s full semantic-memory test coverage was not confirmed.

### What needs to be implemented

Add tests for:

- seed story indexing
- source article indexing
- visual evidence indexing
- agent finding indexing
- chunking
- retrieval filtering
- fake embedding fallback
- LM Studio provider mocking
- vector-store adapter behavior once added

### Suggested test files

- `tests/test_semantic_memory_chunking.py`
- `tests/test_semantic_memory_retrieval.py`
- `tests/test_embedding_provider_lmstudio.py`
- `tests/test_vector_store_lancedb_adapter.py`

### Acceptance criteria

- Fake embeddings make tests deterministic.
- LM Studio API calls are mocked.
- Semantic retrieval returns expected chunks.
- Metadata filters work correctly.

---

## 16. Add visual/social evidence tests

**Status:** Incomplete / not confirmed

### Current state

The visual evidence pipeline exists, but screenshot capture is fallback-only and test coverage for social resolution was not confirmed.

### What needs to be implemented

Add tests for:

- social URL canonicalization
- platform detection
- oEmbed success
- oEmbed failure fallback
- screenshot capture fallback
- future screenshot success
- visual evidence record persistence
- report limitation text when visual evidence fails

### Suggested test files

- `tests/test_social_post_resolver.py`
- `tests/test_screenshot_capture_service.py`
- `tests/test_visual_evidence_service.py`
- `tests/test_visual_evidence_limitations.py`

### Acceptance criteria

- Unsupported platforms fail gracefully.
- Supported platforms produce canonical URLs.
- Screenshot failures are limitations, not fatal errors.
- Visual evidence never overclaims from metadata-only records.

---

## 17. Add report output regression tests

**Status:** Incomplete / not confirmed

### Current state

The deterministic renderer exists, and CrewAI output parsing is improved. The remaining risk is regression: duplicated reports, malformed JSON, empty matrix fields, or invalid source IDs.

### What needs to be implemented

Add regression tests for:

- no report-inside-report duplication
- no duplicate Source Matrix
- no duplicate All Sources section
- no Markdown headings from crew payload inside structured JSON
- source findings mapped to the correct source IDs
- empty source findings repaired or warned

### Suggested test files

- `tests/test_report_renderer_no_duplication.py`
- `tests/test_report_payload_extraction.py`
- `tests/test_source_matrix_key_framing.py`
- `tests/test_report_validator_source_findings.py`

### Acceptance criteria

- Final rendered report has exactly one Source Matrix.
- Final rendered report has exactly one All Sources/Citations section.
- Structured JSON does not leak raw Markdown report content.
- Source Matrix key-framing cells are populated or explicitly limited.

---

## 18. Add benchmark-driven tuning / diagnostics harness

**Status:** Partially implemented

### Current state

The repo has diagnostics and observability hooks, benchmark fixtures, a deterministic benchmark runner, persisted diagnostics export, a static HTML benchmark dashboard, and an opt-in live pipeline benchmark mode. Live mode runs fixture seeds through `AnalysisService.analyze()` and folds completed story IDs into the same persisted diagnostics metrics.

### What needs to be implemented

Create a small benchmark suite using known test stories.

The benchmark should track:

- source recall
- source precision
- bucket coverage
- RSS precision
- candidate rejection reasons
- semantic retrieval quality
- visual evidence fallback rate
- report validation warnings
- runtime

### Suggested files / areas

- New: `benchmarks/`
- New: `scripts/run_retrieval_benchmark.py`
- New: `scripts/export_diagnostics_report.py`
- Possibly new simple HTML/Markdown diagnostics output

### Acceptance criteria

- A developer can run one command and see retrieval quality across fixture stories.
- Benchmark output includes per-story and aggregate metrics.
- Regressions are obvious.

### Current implementation

- `python scripts/run_retrieval_benchmark.py --format markdown`
- `python scripts/run_retrieval_benchmark.py --format json`
- `python scripts/run_retrieval_benchmark.py --format html`
- `python scripts/run_retrieval_benchmark.py --diagnostics-story-id <story_id> --format html --output benchmark.html`
- `python scripts/run_retrieval_benchmark.py --live-run --live-limit 1 --format markdown`
- Optional CI-strict mode: `--fail-on-regression`

The runner reports fixture count, candidate count, precision, recall, accuracy, false positives, false negatives, bucket coverage, warnings, and failed fixture count. It can also include persisted diagnostics metrics for selected story IDs, including RSS acceptance, semantic-scored candidate count, visual fallback rate, report-validation warning count, failed story count, and runtime. Live mode is intentionally opt-in because it can call configured providers/search/screenshot capture and writes to the configured database. Completed analyses now persist a dedicated `report_validation_warnings_json` snapshot, and diagnostics export falls back to visual limitations plus missing buckets only for older runs without that snapshot. Current fixture output makes existing wrong-event false positives visible.

### Remaining work

- Validate live benchmark mode against the intended provider/search configuration and capture representative baseline outputs.
- Backfill or ignore older runs that predate `report_validation_warnings_json`.
- Decide whether the static HTML export should grow into an interactive dashboard.

---

## 19. Add diagnostics API or CLI access if not already exposed

**Status:** Partially implemented at service layer / unclear externally

### Current state

`AnalysisService` has methods for:

- `get_diagnostics(story_id)`
- `get_handoff(story_id, stage)`

But external API/CLI exposure was not confirmed.

### What needs to be implemented

Expose diagnostics and handoffs through whichever interfaces the project supports.

Possible endpoints:

- `GET /analysis/{story_id}/diagnostics`
- `GET /analysis/{story_id}/handoff/{stage}`

Possible CLI commands:

- `research-agent diagnostics <story_id>`
- `research-agent handoff <story_id> <stage>`

### Suggested files / areas

- API route files
- CLI command files
- `src/services/analysis_service.py`

### Acceptance criteria

- User can retrieve candidate census after a run.
- User can retrieve bucket lane attempts after a run.
- User can retrieve visual evidence limitations after a run.
- User can retrieve agent handoff payloads after a run.

---

## 20. Improve configuration validation and user-facing errors

**Status:** Mostly implemented

### Current state

Many important features are controlled by config flags. Several advanced features are off by default. That is fine, but users need clear errors when they enable something without the required dependencies/settings.

Latest continuation adds `research-agent health`, which reports readiness for database/schema, LLM provider configuration, embedding provider/model, vector store backend, screenshot capture, OCR status, and migration state. The command exits non-zero on errors and supports `--strict` to also fail on warnings. When screenshot OCR is enabled, health now executes a tiny local image through `pytesseract` to verify the system OCR path, not just the Python package import.

### What needs to be implemented

Add validation for combinations such as:

- semantic scoring enabled but embedding provider is fake
- LM Studio provider selected but model is missing
- vector store selected but dependency is unavailable
- screenshot capture enabled but Playwright/browser is not installed
- OCR enabled but OCR engine is unavailable

### Suggested files / areas

- `src/core/config.py`
- `src/core/embedding_provider.py`
- `src/services/semantic_memory_service.py`
- `src/services/screenshot_capture_service.py`
- Startup / CLI health-check code

### Acceptance criteria

- Misconfiguration produces clear warnings or errors.
- Fail-open and fail-closed behavior is respected.
- Health check command reports readiness for:
  - LLM provider
  - embedding provider
  - vector store
  - screenshot capture
  - database migrations

### Remaining work

- Health check verifies Playwright browser binaries by launching Chromium when screenshot capture is enabled.
- OCR is optional and default-off; when enabled, health verifies `pytesseract` with a tiny local OCR smoke test.
- Alembic migration chain is still absent, so health reports startup schema sync as the current migration readiness state.

---

# Feature-by-Feature Status Summary

## Retrieval and source balancing

### RSS-first retrieval

**Status:** Mostly implemented, needs tests and tuning

Implemented pieces:

- RSS retrieval service exists.
- RSS-first setting exists and defaults to enabled.
- RSS is part of the planned search phases.
- RSS story matching uses structured story identity.

Remaining work:

- Add precision tests.
- Add diagnostics for accepted/rejected RSS candidates.
- Tune thresholds using benchmark stories.

---

### Bias bucket planning

**Status:** Mostly implemented, needs tests

Implemented pieces:

- Required bucket groups exist.
- Optional center exists.
- Exact-bias ordering exists.
- Seed-aware probe sequence exists.
- Probe quotas and result quotas exist.

Remaining work:

- Add tests proving bucket fairness.
- Add better run diagnostics around quota exhaustion.
- Confirm exact-bias caps behave correctly in all edge cases.

---

### Round-robin bucket probing

**Status:** Mostly implemented, needs hardening

Implemented pieces:

- Bucket round-robin scheduler exists.
- Bucket lane attempts are recorded.
- Missing bucket explanations exist.

Remaining work:

- Avoid flattening/truncating query families too early.
- Add tests proving required lanes are actually probed.
- Add per-family diagnostics.

---

### Strict bucket enforcement

**Status:** Mostly implemented

Implemented pieces:

- Strict enforcement setting exists.
- Missing required buckets raise an error.
- Missing bucket diagnostics exist.

Remaining work:

- Allow per-run override through API/options.
- Improve user-facing error messages with candidate census summary.

---

## Semantic layer

### LM Studio embeddings

**Status:** Implemented but disabled by default

Implemented pieces:

- LM Studio embedding provider exists.
- OpenAI-compatible `/embeddings` call is implemented.
- Fake embedding provider exists for deterministic tests.

Remaining work:

- Add health-check validation.
- Add integration/mocking tests.
- Add per-run provider/model override.

---

### Semantic memory

**Status:** Partially implemented

Implemented pieces:

- SQL semantic documents exist.
- SQL semantic chunks exist.
- Seed story indexing exists.
- Source article indexing exists.
- Visual evidence indexing exists.
- Agent finding indexing exists.
- Agent context building exists.

Remaining work:

- Add real vector backend.
- Add vector metadata filtering.
- Add migration tests.
- Add retrieval quality tests.

---

### Semantic candidate scoring

**Status:** Partially implemented

Implemented pieces:

- Candidate semantic scorer exists.
- Title/lede/chunk similarity fields exist.
- Source aggregation can use semantic scores.

Remaining work:

- Enable/configure real embeddings.
- Add tests.
- Add better diagnostics.
- Confirm ranking impact in benchmarks.

---

### Semantic query expansion

**Status:** Partially implemented

Implemented pieces:

- Deterministic query families exist.
- Optional LLM query expansion exists.

Remaining work:

- Use semantic memory for expansion.
- Preserve query families through retrieval.
- Add tests for paraphrase quality and fallback behavior.

---

## Visual evidence layer

### Social-post resolver

**Status:** Partially implemented

Implemented pieces:

- URL canonicalization exists.
- Platform detection exists.
- X/Twitter oEmbed exists.
- TikTok oEmbed exists.

Remaining work:

- Add or improve handling for Instagram, Threads, Facebook, and Truth Social.
- Add real screenshot fallback.
- Add tests.

---

### Screenshot capture

**Status:** Incomplete

Implemented pieces:

- Structured fallback schema exists.
- Capture method returns provenance and limitation info.

Remaining work:

- Add real Playwright capture.
- Save artifacts.
- Add OCR if feasible.
- Add tests.

---

### Visual evidence analysis

**Status:** Partially implemented

Implemented pieces:

- Image analysis can route through visual LLM provider.
- Social posts route through resolver and screenshot service.
- Visual evidence records are persisted.
- Visual evidence can be indexed into semantic memory.

Remaining work:

- Real screenshots.
- Real OCR.
- Better limitation wording.
- Tests for fallback vs true visual evidence.

---

## Persistence and handoffs

### Candidate census

**Status:** Mostly implemented

Implemented pieces:

- Candidate decisions exist.
- Candidate census exists.
- Missing bucket explanations exist.
- Retrieval candidates are persisted.

Remaining work:

- Add more tests.
- Add API/CLI visibility if missing.
- Add benchmark metrics.

---

### Source metadata persistence

**Status:** Mostly implemented

Implemented pieces:

Sources now persist:

- extraction method
- extraction error
- extraction error code
- HTTP status
- relevance score
- source score
- bucket label
- exact bias
- coverage type
- OG image URL
- embedded post URLs
- image alt text
- media captions
- relevance diagnostics
- media diagnostics
- key framing

Remaining work:

- Add migration tests.
- Confirm all fields are populated consistently.

---

### Agent handoffs

**Status:** Mostly implemented

Implemented pieces:

- Agent handoff model exists.
- Post-retrieval handoff exists.
- Pre-crew handoff exists.
- Finding-based handoffs exist.

Remaining work:

- Expose handoffs via API/CLI if missing.
- Add tests that handoff payloads are retrievable and useful.

---

## Report layer

### Report duplication fix

**Status:** Mostly implemented

Implemented pieces:

- Crew output extraction avoids blindly stringifying the entire CrewAI result.
- Structured section parsing exists.
- Markdown-shaped crew payloads can be rejected.
- Deterministic renderer owns headings, Source Matrix, and citations.

Remaining work:

- Add regression tests.
- Ensure malformed CrewAI output triggers repair/failure instead of bad final reports.

---

### Source Matrix key framing

**Status:** Mostly implemented but needs repair path

Implemented pieces:

- Source findings schema exists.
- Report-writer prompt asks for source findings.
- Renderer displays key framing and notable claim.
- Source findings are persisted.

Remaining work:

- Add deterministic fallback or repair step for missing findings.
- Add validation that every retained source has a finding.
- Add tests.

---

# Suggested Implementation Order

## Phase 1 — Stabilize current architecture

1. Add missing tests for bucket round-robin fairness.
2. Add RSS story-matching precision tests.
3. Add report duplication and Source Matrix tests.
4. Add source-finding validation / repair.
5. Improve diagnostics output for missing buckets and retrieval failures.

## Phase 2 — Make visual evidence real

1. Implement Playwright screenshot capture.
2. Persist screenshot artifacts.
3. Add optional OCR.
4. Improve social-post platform handling.
5. Add visual evidence tests.

## Phase 3 — Make semantic memory real

1. Add LanceDB vector-store adapter.
2. Wire semantic memory to LanceDB.
3. Add vector metadata filters.
4. Add semantic retrieval tests.
5. Add LM Studio embedding provider tests.

## Phase 4 — Make configuration and API clean

1. Add per-run analysis options.
2. Persist run options.
3. Add diagnostics API/CLI access.
4. Add config validation / health check.
5. Add fail-open/fail-closed tests.

## Phase 5 — Benchmark and tune

1. Add benchmark fixture stories.
2. Track retrieval metrics.
3. Track visual fallback rates.
4. Track report validation warnings.
5. Tune RSS thresholds, relevance weights, query family behavior, and semantic scoring.

---

# Concrete Test Checklist

## Retrieval tests

- `tests/test_bucket_round_robin_probe_scheduler.py`
- `tests/test_bucket_probe_quotas.py`
- `tests/test_exact_bias_caps.py`
- `tests/test_strict_bucket_enforcement.py`
- `tests/test_rss_story_matching_precision.py`
- `tests/test_rss_must_not_have_terms.py`
- `tests/test_rss_marker_overlap.py`

## Semantic tests

- `tests/test_semantic_memory_chunking.py`
- `tests/test_semantic_memory_retrieval.py`
- `tests/test_embedding_provider_lmstudio.py`
- `tests/test_vector_store_lancedb_adapter.py`
- `tests/test_hybrid_relevance_scoring.py`

## Visual evidence tests

- `tests/test_social_post_resolver.py`
- `tests/test_screenshot_capture_service.py`
- `tests/test_visual_evidence_service.py`
- `tests/test_visual_evidence_limitations.py`

## Report tests

- `tests/test_report_renderer_no_duplication.py`
- `tests/test_report_payload_extraction.py`
- `tests/test_source_matrix_key_framing.py`
- `tests/test_report_validator_source_findings.py`

## Database / migration tests

- `tests/test_sql_migration_semantic_memory.py`
- `tests/test_database_schema_upgrade.py`
- `tests/test_retrieval_candidate_persistence.py`
- `tests/test_visual_evidence_persistence.py`
- `tests/test_source_findings_persistence.py`

---

# Practical Definition of Done

The branch should not be considered complete until all of these are true:

1. A run cannot accidentally stop after finding only same-side sources unless diagnostics prove required opposing lanes were fairly probed and failed.
2. RSS retrieval can distinguish same story from same general topic.
3. Semantic memory uses a real vector backend, not only SQL and fake vector IDs.
4. LM Studio embeddings can be enabled and verified through tests/health checks.
5. Social-post evidence can produce real screenshot artifacts when publicly accessible.
6. Visual evidence clearly separates observable facts from interpretation.
7. Source Matrix key-framing is always populated, repaired, or explicitly marked as limited.
8. Database schema changes are handled through migrations.
9. Diagnostics and handoffs are accessible after a run.
10. Benchmarks can measure retrieval quality and detect regressions.

---

# Short Version for a Coding Agent

Implement the remaining hardening work in this order:

1. Add regression tests for bucket fairness, RSS precision, report duplication, and Source Matrix findings.
2. Add Source Matrix repair/validation so missing `source_findings` do not silently render as empty claims.
3. Implement real Playwright screenshot capture and artifact persistence.
4. Add optional OCR for screenshots.
5. Expand social-post resolver behavior beyond X/Twitter and TikTok oEmbed.
6. Add LanceDB vector-store adapter for semantic memory.
7. Wire semantic retrieval to the vector store instead of SQL-only re-ranking.
8. Preserve query families through bucket-lane retrieval instead of flattening/truncating to four queries.
9. Add per-run analysis options for semantic memory, visual evidence, strictness, embedding model, and vector backend.
10. Replace startup schema patching with real Alembic migrations.
11. Expose diagnostics/handoffs through API or CLI.
12. Add benchmark scripts and fixture stories for tuning retrieval behavior.

The repo has many of the right classes and schemas now. The remaining job is to turn scaffolding into durable behavior, add real backends where placeholders exist, expose controls cleanly, and lock it down with tests.
