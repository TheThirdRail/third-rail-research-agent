# Semantic Memory and Vector Search Checklist

Last updated: 2026-04-30

## Acceptable Final Result For This Documentation Pass

Historical note: this section describes the original documentation-only planning
pass. Later implementation passes intentionally edited runtime code for the
checked phases below.

- [x] Create `docs/semantic-memory-vector-search-implementation-guide.md`.
- [x] Create `semantic-memory-vector-search-checklist.md`.
- [x] Keep this pass documentation-only.
- [x] Do not edit runtime code, config, dependencies, migrations, tests, or
  existing user work.
- [x] Give the future coding agent a clear endpoint and phased checklist.

## Stop Conditions For Future Coding Agents

- [ ] Ask before adding dependencies such as `lancedb`, `chromadb`, or
  `sentence-transformers`.
- [ ] Ask before changing public API response shapes.
- [ ] Ask before replacing the current source selection policy.
- [ ] Ask before running destructive vector store resets outside test data.
- [ ] Do not claim Codex OAuth supports embeddings unless `/v1/embeddings` has
  been implemented and tested.

## Phase 1: Semantic Query Expansion

- [x] Add config flags with expansion disabled by default.
- [x] Add a lightweight LLM query expansion method to `StoryParserService`.
- [x] Use `LLMRouter.complete()` with a short strict-JSON prompt.
- [x] Generate neutral, conservative/right, progressive/left, and
  procedural/legal query variants.
- [x] Validate output as short search phrases.
- [x] Dedupe semantic queries against deterministic `query_pack`.
- [x] Fail open to deterministic queries on model/config errors.
- [x] Add tests for disabled default, successful expansion, invalid JSON, and
  fail-open behavior.

Acceptance:

- [x] A Cuba blockade/embargo/sanctions story produces useful wording variants.
- [x] No new CrewAI agent is added.
- [x] Current Codex OAuth chat bridge remains compatible.

## Phase 2: Semantic Schema And Service Skeleton

- [x] Add `SemanticDocument` SQLAlchemy model.
- [x] Add `SemanticChunk` SQLAlchemy model.
- [x] Add idempotent schema sync or migration coverage.
- [x] Add fake deterministic embedding provider for tests.
- [x] Add LM Studio OpenAI-compatible embeddings provider behind the abstraction.
- [ ] Add local sentence-transformers provider behind an abstraction.
- [ ] Add OpenAI/LiteLLM embedding provider behind the same abstraction.
- [ ] Add LanceDB vector store adapter.
- [x] Add `SemanticMemoryService` with chunking and SQL document creation.
- [x] Add tests for model imports, schema sync, chunking, and metadata validation.

Acceptance:

- [x] Semantic documents and chunks can be created in SQL.
- [x] Tests do not require network or paid embedding calls.
- [x] Vector records are treated as rebuildable index entries.

## Phase 3: Retained Source Indexing

- [x] Call semantic indexing after `Story` and retained `Source` rows are
  persisted in `AnalysisService`.
- [x] Index seed story text and parsed `StoryPacket` summary.
- [x] Index retained source article chunks.
- [x] Store provider, model, dimensions, chunk hash, and vector IDs.
- [x] Log semantic diagnostics without exposing secrets.
- [x] Add `rebuild_story_index(story_id)`.
- [x] Add `delete_story_index(story_id)` for test/admin cleanup.

Acceptance:

- [x] One story with three retained sources can be chunked, embedded, stored, and
  queried by `story_id`.
- [x] Deleting the vector store does not lose canonical source text.

## Phase 4: Candidate Semantic Relevance

- [x] Decide whether to move `Story` creation before source gathering or use a
  temporary semantic run ID. Current choice: in-memory seed vector for candidate
  scoring, with persisted semantic memory still after `Story`/`Source` rows.
- [x] Index/query a seed story vector before candidate scoring.
- [x] Compute semantic similarity after candidate extraction.
- [x] Extend `RelevanceScore` with semantic and distinctive-term fields.
- [x] Keep deterministic rejection rules in force.
- [x] Add fixtures for same-event/different-wording and same-person/wrong-event.

Acceptance:

- [x] Same-event articles with different wording are accepted.
- [x] Same-person wrong-event articles are rejected or downgraded.
- [x] Semantically similar articles missing distinctive event markers are not
  direct coverage.

## Phase 5: Bias-Balanced Retention

- [x] Feed semantic similarity into `score_candidate()` as event similarity.
- [x] Preserve exact-bias and bucket caps.
- [x] Continue probing for missing required buckets.
- [x] Keep strict bucket enforcement behavior.
- [x] Add a fixture with five left, one center, and one right candidate.

Acceptance:

- [x] Discoverable opposite-side coverage cannot be skipped just because same-side
  candidates filled the retained source max.

## Phase 6: Agent Context Retrieval

- [x] Add task-specific retrieval helpers in `SemanticMemoryService`.
- [x] Retrieve fact-focused chunks for the fact extractor.
- [x] Retrieve language/framing chunks for the rhetorical analyst.
- [x] Retrieve bias-bucket grouped chunks for the narrative analyzer.
- [x] Retrieve citation-ready chunks and structured findings for the report writer.
- [x] Include source IDs and chunk IDs in context.
- [x] Avoid full-article prompt dumps.

Acceptance:

- [x] Each major agent receives relevant source-linked chunks for its task.
- [x] Later agents are not forced to rely only on previous-agent summaries.

## Phase 7: Agent Findings And Visual Evidence Memory

- [x] Store structured fact extraction findings as semantic documents.
- [x] Store rhetorical findings as semantic documents.
- [x] Store narrative findings and coverage asymmetry as semantic documents.
- [x] Store visual evidence records as semantic documents.
- [x] Keep visual fields separated: observable, reported context,
  interpretation, legal characterization.
- [x] Add retrieval tests for prior findings and visual observations.

Acceptance:

- [x] Prior findings can be retrieved by meaning and source linkage.
- [x] Final reports separate visible media evidence from political/legal claims.

## Final Implementation Acceptance

- [x] Semantic query expansion improves search recall.
- [x] SQL remains the source of truth.
- [x] Vector storage can be rebuilt from SQL.
- [x] Semantic records always include source/story linkage metadata.
- [x] Deterministic relevance gates still prevent wrong-event matches.
- [x] Bias-balanced source selection remains authoritative.
- [x] Semantic failures fail open in development with diagnostics.
- [x] Tests cover query expansion, chunking, indexing, retrieval, scoring, source
  balance, agent memory, and visual evidence separation.
