# Research Agent Semantic Memory Handoff

**Date:** 2026-04-30
**Branch state:** working tree has active uncommitted implementation and doc changes.
**Purpose:** hand off the semantic query expansion and semantic memory work after completing the current implementation guide.

## What Was Done

1. Created the semantic memory planning docs:
   - `docs/semantic-memory-vector-search-implementation-guide.md`
   - `semantic-memory-vector-search-checklist.md`
2. Implemented Phase 1 semantic query expansion:
   - Added disabled-by-default config flags.
   - Added guarded LLM query expansion in `StoryParserService`.
   - Uses `LLMRouter.complete()` for chat completion, so Codex OAuth bridge testing works for this part.
   - Validates short JSON query output, dedupes against deterministic `query_pack`, and fails open.
3. Implemented dependency-light Phase 2 semantic memory scaffolding:
   - Added `SemanticDocument` and `SemanticChunk` SQLAlchemy models.
   - Added SQL-backed `SemanticMemoryService`.
   - Added deterministic `FakeEmbeddingProvider` for tests.
   - Added LM Studio OpenAI-compatible embeddings provider using existing `httpx` and LM Studio config helpers.
4. Implemented Phase 3 retained-source SQL indexing:
   - Added semantic memory config flags.
   - Wired `AnalysisService` to index seed story and retained source article chunks after `Story` and `Source` rows are persisted.
   - Added `get_chunks_for_story`, `delete_story_index`, and `rebuild_story_index`.
   - Kept semantic memory disabled by default and fail-open when indexing fails.
5. Implemented Phase 4 candidate semantic relevance:
   - Chose the temporary in-memory semantic run ID path instead of moving `Story` creation before source gathering.
   - Added `CandidateSemanticScorer` to embed a seed story vector before candidate scoring and compare extracted candidates against it.
   - Extended `RelevanceScore` with `semantic_similarity`, `distinctive_term_overlap`, and `direct_evidence_score`.
   - Kept deterministic direct-coverage gates in force, including distinctive numeric markers like `8647`.
   - Added disabled-by-default `SEMANTIC_CANDIDATE_SCORING_ENABLED` and `SEMANTIC_FAIL_OPEN` settings.
6. Implemented Phase 5 bias-balanced retention with semantic scores:
   - `score_candidate()` now accepts semantic similarity as the event similarity input when available.
   - `SourceAggregatorService` passes candidate semantic similarity into source scoring while preserving deterministic relevance rejection first.
   - Added a five-left, one-center, one-right fixture that keeps discoverable opposite-side coverage despite same-side volume.
   - Preserved exact-bias caps, bucket caps, probing, and strict bucket enforcement behavior.
7. Implemented Phase 6 agent context retrieval:
   - Added typed `SemanticRetrievalResult` output and task-specific retrieval helpers in `SemanticMemoryService`.
   - Added SQL-backed retrieval from `SemanticChunk` rows with metadata filters.
   - For non-fake embedding providers, retrieval re-embeds SQL chunk text on demand until an external vector store adapter is approved.
   - For fake embeddings, retrieval uses deterministic lexical ranking so tests and local dry-runs do not depend on hash-vector similarity.
   - Added formatted semantic context blocks for `fact_extractor`, `rhetorical_analyst`, `narrative_analyzer`, and `report_writer`.
   - Context blocks include semantic chunk/document IDs, SQL source IDs, and `S1`/`S2` source refs when available, with capped excerpts instead of full article dumps.
   - Wired `AnalysisService` to build and pass `agent_contexts` into `run_analysis()` only after semantic memory indexing succeeds.
8. Implemented Phase 7 agent findings and visual evidence memory:
   - Added `SemanticMemoryService.index_visual_evidence()` for `visual_evidence` semantic documents.
   - Visual evidence canonical text and metadata keep observable text, visible symbols/numbers, observable objects, reported context, interpretation, and legal characterization separated.
   - Added `SemanticMemoryService.index_structured_finding()` for typed `fact_claims`, `rhetoric_findings`, `narrative_findings`, and `coverage_asymmetry` documents.
   - `AnalysisService` now indexes visual evidence before semantic agent-context retrieval, so same-run fact/report prompts can retrieve observable media records.
   - `AnalysisService` indexes structured report-section findings after the `Analysis` row is persisted. These are available for later retrieval, rebuilds, and follow-up runs.
   - Finding metadata includes `analysis_id`, document type, section fields, and parsed `S1`/`S2`-style source refs when present in section text.
9. Updated `.env.example` with semantic query and semantic memory settings, including `SEMANTIC_TOP_K=4`.
10. Updated tests:
   - `tests/test_story_parser_and_relevance.py`
   - `tests/test_semantic_memory_service.py`
   - `tests/test_end_to_end_analysis.py`
   - `tests/test_analysis_crew_structure.py`
   - `tests/test_source_aggregator_service.py`
   - `tests/test_hardening_services.py`
11. Updated `semantic-memory-vector-search-checklist.md` and `docs/semantic-memory-vector-search-implementation-guide.md` to mark Phase 7 and final semantic acceptance complete.

## Current Verification

Full test suite:

```text
python -m pytest -q
198 passed, 160 warnings
```

Focused lint:

```text
python -m ruff check src/services/semantic_memory_service.py src/services/analysis_service.py tests/test_semantic_memory_service.py tests/test_end_to_end_analysis.py
All checks passed
```

Whitespace check:

```text
git diff --check
```

No whitespace errors were reported. Git printed existing Windows line-ending warnings: `LF will be replaced by CRLF the next time Git touches it`.

Warnings are existing SQLAlchemy `datetime.utcnow()` deprecation warnings from model defaults.

## LM Studio Local Embeddings

To test semantic memory indexing with LM Studio:

```env
SEMANTIC_MEMORY_ENABLED=true
EMBEDDING_PROVIDER=lmstudio
EMBEDDING_MODEL=<your-loaded-embedding-model-id>
LM_STUDIO_API_BASE=http://localhost:1234/v1
LM_STUDIO_API_KEY=lm-studio
```

The current Codex OAuth bridge supports semantic query expansion through chat completion, but it still does not support embeddings because `/v1/embeddings` is not implemented in the bridge.

## In Progress / Next Steps

Priority order:

1. Semantic guide Phases 1-7 are complete. Start the next session by reviewing the diff and deciding whether to commit this semantic-memory work.
2. Optional provider/vector-store work requires explicit approval before adding dependencies:
   - local `sentence-transformers` provider
   - OpenAI/LiteLLM embedding provider
   - LanceDB vector adapter
3. Run a manual local trial with `SEMANTIC_MEMORY_ENABLED=true` and LM Studio embeddings if you want runtime confidence beyond fake-provider tests.
4. If shifting back to the broader `dev-branch-report.md` backlog, run a fresh sample report and re-evaluate report composition, source balance, and visual-evidence behavior against that output.

## Still Unchecked In Checklist

Intentional deferrals:

- `sentence-transformers` provider: requires dependency approval.
- OpenAI/LiteLLM embedding provider: provider/budget decision still needed.
- LanceDB vector adapter: requires dependency approval.

Ongoing guardrails in the checklist remain unchecked because they are stop conditions, not one-time implementation tasks:

- Ask before adding dependencies such as `lancedb`, `chromadb`, or `sentence-transformers`.
- Ask before changing public API response shapes.
- Ask before replacing the current source selection policy.
- Ask before running destructive vector store resets outside test data.
- Do not claim Codex OAuth supports embeddings unless `/v1/embeddings` has been implemented and tested.

## Gotchas

- Do not claim Codex OAuth supports embeddings unless `/v1/embeddings` is added and tested.
- `SEMANTIC_MEMORY_ENABLED` is disabled by default. This is deliberate.
- `SEMANTIC_CANDIDATE_SCORING_ENABLED` is also disabled by default.
- Automated tests should keep using fake/mocked embeddings, not a live LM Studio server.
- `AnalysisService` still creates the `Story` after source gathering. Candidate semantic scoring uses an in-memory seed vector for pre-retention scoring, then retained semantic memory is persisted after SQL rows exist.
- The vector store is not implemented yet. Current semantic memory is SQL-backed with fake vector IDs or LM Studio-generated dimensions stored on chunks.
- Phase 6 retrieval currently reads canonical SQL chunks and re-embeds them on demand for non-fake providers. It is not a LanceDB/Chroma vector-store search yet.
- Fake embeddings intentionally use lexical ranking for retrieval. The fake provider's hash vectors are deterministic but not semantically meaningful.
- Agent semantic contexts are fail-open: if indexing or retrieval fails, analysis continues with the compact source manifest and no semantic context blocks.
- Phase 7 visual evidence is indexed before same-run semantic context retrieval. Phase 7 structured agent findings are indexed only after the final structured sections and `Analysis` row exist, so they help later retrieval and follow-up runs rather than the current run's earlier CrewAI tasks.
- Structured finding `source_refs` metadata is extracted from `S1`/`S2` markers in section text. If the crew omits those markers, the semantic document still has story/analysis linkage but source refs may be empty.
- There is no separate `INDEX_AGENT_FINDINGS` setting in the current implementation. Typed findings are indexed when `SEMANTIC_MEMORY_ENABLED=true`.

## Git State Notes

Recent commits:

```text
1d9f3bb feat: complete research agent testing, reporting, and integration
4d00e72 feat: finalize research agent integration and add end-to-end test
8f79f06 feat: integrate pipeline hardening services
1217a98 docs: add Deep-RSS research and comprehensive source list
08dc13b docs: rewrite README.md and step-by-step.md
```

Current working tree remains uncommitted and includes semantic implementation/docs plus pre-existing local items. Known unrelated working tree items seen before this handoff:

- `.serena/project.yml`
- `brainstorm.md`
- `test_rss.py`

Do not revert those unless the user explicitly asks.
