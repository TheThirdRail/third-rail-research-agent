# Semantic Memory and Vector Search Implementation Guide

Last updated: 2026-04-30

## Purpose

This guide describes how to add semantic search and semantic memory to the
Research Agent without replacing the deterministic source selection system that
is already working.

The immediate product goal is to help the agent understand that two articles can
cover the same underlying event even when outlets use different wording,
especially across ideological frames. The longer-term goal is to preserve
source-grounded article meaning across the analysis workflow so later agents do
not reason only from short excerpts or another agent's summary.

This is a guide for a future coding agent. The coding phase that created this
file should only write documentation and a checklist. It should not implement
runtime code.

## Current Repo Ground Truth

The current pipeline already has useful structure. Build on it.

- `StoryParserService` creates a `StoryPacket` with a canonical headline,
  actors, action verbs, distinctive terms, visual descriptors, must-have terms,
  must-not-have terms, and `query_pack`.
- `SourceAggregatorService` uses `story_packet.query_pack` when building search
  queries, gathers RSS/search results, extracts article text, resolves bias,
  scores relevance, checks duplicates, and applies balanced source policy.
- `RelevanceScorerService` scores entity overlap, event overlap, time overlap,
  place overlap, topic match, novelty, and coverage type.
- `BalancedSourcePlanner` and `source_scoring.py` enforce bucket-aware selection.
  Semantic similarity must support this policy, not replace it.
- `AnalysisService` currently creates the `Story` database row after source
  gathering. This matters because candidate scoring happens before persistent
  `story_id` and `source_id` values exist.
- `LLMRouter` currently supports chat/completion calls through LiteLLM and has
  Codex OAuth bridge guards for OpenAI-compatible chat completion testing.
- The local Codex OAuth bridge currently exposes `/v1/models`,
  `/v1/chat/completions`, and `/v1/responses`. It does not expose
  `/v1/embeddings`.

The safest architecture is:

```text
SQL database = source of truth
Vector database = rebuildable semantic retrieval index
LLM calls = query expansion, reasoning, and synthesis
Deterministic services = factual constraints and source-balance policy
Report renderer = final presentation
```

## Recommended Architecture

### Build In Two Semantic Layers

Use two related but separate capabilities.

1. Semantic query expansion
   - Add a lightweight LLM call in `StoryParserService`.
   - Output ideologically varied search queries.
   - Append safe, deduplicated queries to `StoryPacket.query_pack`.
   - This does not require a new CrewAI agent.
   - This does work with the current Codex OAuth chat bridge because it uses
     `LLMRouter.complete()`.

2. Semantic memory and vector retrieval
   - Add a dedicated embedding provider wrapper, vector store adapter, SQL
     semantic document/chunk records, and `SemanticMemoryService`.
   - Do not call vector storage directly from CrewAI agents.
   - Do not assume OpenAI embeddings work through the current Codex bridge.
   - For local/Codex testing, use deterministic fake embeddings in tests and a
     local sentence-transformers provider for manual local trials.

### Recommended First Vector Store

Use LanceDB as the default implementation target.

Why:

- It runs embedded from a local filesystem path, which fits this repo's local
  SQLite-first shape.
- It supports vector search plus SQL-style metadata filtering.
- It has a cleaner path from local development to production than an ad hoc
  FAISS index.

Accept ChromaDB as a prototype alternative if the coding agent needs the fastest
working demo. Do not begin with FAISS unless there is a specific performance or
hosting reason.

Recommended config names:

```text
SEMANTIC_MEMORY_ENABLED=false
SEMANTIC_QUERY_EXPANSION_ENABLED=false
SEMANTIC_CANDIDATE_SCORING_ENABLED=false
VECTOR_STORE_PROVIDER=lancedb
VECTOR_STORE_PATH=data/vector_store
EMBEDDING_PROVIDER=local_sentence_transformers
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_BATCH_SIZE=32
SEMANTIC_TOP_K=8
SEMANTIC_MIN_SIMILARITY=0.72
SEMANTIC_DIRECT_COVERAGE_THRESHOLD=0.78
SEMANTIC_CONTEXTUAL_THRESHOLD=0.62
SEMANTIC_FAIL_OPEN=true
INDEX_AGENT_FINDINGS=true
INDEX_FINAL_REPORT_SECTIONS=false
```

Default both semantic features to disabled until each phase has tests.

### Recommended Embedding Strategy

Add a new embedding abstraction instead of overloading `LLMRouter`.

Suggested module:

```text
src/core/embedding_provider.py
```

Suggested interface:

```python
class EmbeddingProvider:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...
```

Providers:

- `fake`: deterministic, test-only embeddings.
- `local_sentence_transformers`: local manual testing and Codex OAuth workflows.
- `openai`: production/provider testing when a real `/v1/embeddings` endpoint and
  key are available.

OpenAI embeddings can use LiteLLM's `embedding()` function or the OpenAI SDK,
but must go through explicit budget/config validation. The current Codex bridge
does not provide embeddings, so do not route embeddings to it unless a future PR
adds `/v1/embeddings`.

## Data Model

Add SQL records for semantic memory. SQL remains authoritative and lets the
vector index be rebuilt.

### `semantic_documents`

One row per source unit before chunking.

Suggested fields:

```text
id
story_id
source_id nullable
analysis_id nullable
agent_name nullable
document_type
title
canonical_text
metadata_json
created_at
updated_at
```

Suggested `document_type` values:

```text
seed_story
source_article
source_article_summary
visual_evidence
agent_finding
fact_claims
rhetoric_findings
narrative_findings
coverage_asymmetry
report_section
```

### `semantic_chunks`

One row per chunk with a corresponding vector record.

Suggested fields:

```text
id
semantic_document_id
story_id
source_id nullable
chunk_index
chunk_text
chunk_hash
token_count approximate
vector_store_id
embedding_provider
embedding_model
embedding_dimensions
metadata_json
created_at
```

### Vector Metadata

Every vector record must include enough metadata to filter precisely:

```json
{
  "story_id": "...",
  "source_id": "...",
  "semantic_document_id": "...",
  "semantic_chunk_id": "...",
  "domain": "example.com",
  "url": "https://example.com/article",
  "bias_score": -1,
  "bias_label": "Slight Left",
  "bias_bucket": "left_side",
  "coverage_type": "direct",
  "document_type": "source_article",
  "agent_name": null,
  "chunk_index": 3,
  "published_date": "2026-04-28",
  "created_at": "2026-04-29"
}
```

For agent findings:

```json
{
  "story_id": "...",
  "source_id": "...",
  "semantic_document_id": "...",
  "semantic_chunk_id": "...",
  "document_type": "agent_finding",
  "agent_name": "rhetorical_analyst",
  "finding_type": "loaded_language",
  "claim_id": "...",
  "bias_score": -1,
  "domain": "example.com"
}
```

Keep chunk text in SQL too. The vector DB is an index, not the only storage.

## New Service Layer

Add a dedicated service:

```text
src/services/semantic_memory_service.py
```

Responsibilities:

- create semantic documents
- chunk text
- call the embedding provider
- write vector records
- update SQL chunk records
- query vector store with metadata filters
- return source-grounded retrieval results
- rebuild or delete a story's semantic index

Suggested public methods:

```text
index_seed_story(story_id, story_packet, seed_text, metadata)
index_source_article(story_id, source_id, title, text, metadata)
index_visual_evidence(story_id, source_id, evidence_text, metadata)
index_agent_finding(story_id, source_id, agent_name, finding_type, finding_text, metadata)
search_similar_to_story(story_id, query_text, filters, top_k)
search_for_agent_context(story_id, agent_name, task_name, query_text, filters, top_k)
rebuild_story_index(story_id)
delete_story_index(story_id)
```

Return a typed result object with:

```text
semantic_chunk_id
semantic_document_id
story_id
source_id nullable
chunk_text
similarity
metadata
```

## Chunking

Do not embed whole long articles as one blob.

First-pass chunking policy:

- 500 to 900 tokens per chunk.
- 100 token overlap.
- Preserve paragraph boundaries when reasonable.
- Include title, domain, URL, date, bias, and source identifiers in metadata.
- If extracted text is under about 1,000 tokens, one chunk is acceptable.
- For agent findings, embed one finding or a small related group, not the entire
  final report as a single chunk.

Do not embed:

- raw HTML
- nav text
- cookie banners
- duplicate syndicated copies without metadata
- debug logs
- prompts
- huge unchunked reports

## Phased Implementation

### Phase 1: Semantic Query Expansion

Goal: improve RSS and search recall before adding vector infrastructure.

Implementation:

- Add config:
  - `SEMANTIC_QUERY_EXPANSION_ENABLED=false`
  - `SEMANTIC_QUERY_EXPANSION_MAX_QUERIES=4`
  - `SEMANTIC_QUERY_EXPANSION_AGENT_NAME=semantic_query_expander`
- Add a direct LLM call inside `StoryParserService.parse()` after deterministic
  extraction builds its initial `StoryPacket`.
- Prompt for short search phrases across neutral, left/progressive,
  right/conservative, and procedural/legal frames.
- Require strict JSON output, for example:

```json
{
  "queries": [
    "Senate Republicans Cuba embargo vote",
    "GOP senators block Cuba trade concessions",
    "Republicans uphold Trump Cuba sanctions"
  ],
  "aliases": ["Cuba embargo", "Cuba sanctions"]
}
```

- Validate and sanitize query output:
  - strings only
  - 3 to 9 words
  - no URLs
  - no quotation marks unless already present in deterministic query
  - dedupe case-insensitively
  - cap total `query_pack` length
- Fail open: if the LLM call fails, keep deterministic queries.

Codex OAuth note:

- This phase works with the current bridge because it uses chat completion via
  `LLMRouter.complete()`.
- Keep the prompt below `CODEX_MAX_PROMPT_CHARS`.

Done when:

- A story like "Senate Republicans reject attempt to end Trump's blockade of
  Cuba" produces non-identical semantic queries that can search for "embargo",
  "sanctions", "trade concessions", and "GOP senators" without adding a CrewAI
  agent.
- Existing deterministic parser tests still pass when expansion is disabled.

### Phase 2: Semantic Schema and Service Skeleton

Goal: add rebuildable SQL-backed semantic memory scaffolding without changing
source selection yet.

Implementation:

- Add SQLAlchemy models for `SemanticDocument` and `SemanticChunk`.
- Add relationships from `Story`, `Source`, and `Analysis` only where they reduce
  lookup complexity.
- Extend the idempotent schema sync in `src/database/session.py` or introduce a
  proper migration path consistent with the repo's current startup migration
  style.
- Add `EmbeddingProvider` and a fake test provider.
- Add LanceDB vector store adapter behind a small interface.
- Add `SemanticMemoryService` with chunking and SQL-only document creation first.

Done when:

- The app can create semantic documents and chunks in SQL with fake embeddings.
- Tests can rebuild an index from SQL rows without requiring network access.

### Phase 3: Retained Source Indexing

Goal: persist semantic memory for the sources that were actually retained.

Important repo constraint:

- Today `AnalysisService` creates the `Story` after `gather_sources()`.
- For this phase, avoid large workflow surgery by indexing after the story and
  `Source` rows are persisted.
- Pre-retention candidate semantic scoring comes later.

Implementation:

- In `AnalysisService`, after persisted sources are created, call
  `SemanticMemoryService.index_seed_story()` and
  `index_source_article()` for each retained source when
  `SEMANTIC_MEMORY_ENABLED=true`.
- Store semantic diagnostics in logs or returned metadata:
  - indexed source count
  - chunk count
  - provider
  - model
  - failures
- Fail open in development. If indexing fails, analysis continues with a warning.

Done when:

- Given one story and three retained sources, the system stores seed/source
  semantic documents, chunk rows, and vector IDs.
- `rebuild_story_index(story_id)` can recreate vector records from SQL chunks.

### Phase 4: Candidate Semantic Relevance

Goal: use semantic similarity during candidate scoring while keeping hard
deterministic gates.

Recommended architecture decision:

- Move `Story` creation earlier in `AnalysisService` before source gathering, or
  add an explicit semantic run ID for candidate scoring.
- Prefer moving `Story` creation earlier only after tests cover failure status,
  source persistence, and existing API return behavior.

Current implementation choice:

- Keep `Story` creation after source gathering.
- Use an in-memory seed story vector as the temporary semantic run ID for
  pre-retention candidate scoring.
- Persist retained seed/source semantic memory after `Story` and `Source` rows
  exist, as in Phase 3.

Implementation:

- Index a seed story vector before preflight candidate scoring.
- In `_preflight_search_results()`, after extraction and before deterministic
  relevance rejection, compute semantic similarity against the seed story.
- Extend `RelevanceScore` with:
  - `semantic_similarity`
  - `distinctive_term_overlap`
  - `direct_evidence_score`
- Keep the current rejection behavior for must-have, must-not-have, direct
  coverage, and wrong-event cases.
- Suggested scoring shape:

```text
entity_overlap: 0.20
event_overlap: 0.15
time_overlap: 0.10
place_overlap: 0.05
topic_match: 0.10
distinctive_term_overlap: 0.15
semantic_similarity: 0.20
novelty: 0.05
```

Rules:

- Semantic similarity can raise confidence that different wording is the same
  event.
- Semantic similarity cannot turn an article into direct coverage if mandatory
  distinctive event markers are missing.
- Semantic similarity cannot override must-not-have exclusions.
- Semantic similarity cannot override bias-bucket selection policy.

Done when:

- Same-event/different-wording articles are accepted.
- Same-person/wrong-event articles are rejected or downgraded.
- A semantically similar article missing a distinctive token like `8647` is
  contextual, not direct.

### Phase 5: Bias-Balanced Retention With Semantic Scores

Goal: improve candidate ranking without weakening source balance.

Implementation:

- Feed semantic similarity into `score_candidate()` as the event similarity
  component.
- Continue grouping by exact bias score and broad bucket.
- Continue probing/fallback search for required missing buckets.
- Do not stop after five same-side sources if required opposite-side buckets have
  not been searched or filled.

Done when:

- A candidate pool with five left articles, one center article, and one right
  article with different wording selects balanced coverage instead of filling the
  retained set with one side.

### Phase 6: Agent Context Retrieval

Goal: ground each major agent in task-specific original chunks.

Current implementation choice:

- `SemanticMemoryService` now retrieves source-linked `SemanticChunk` rows from
  SQL and formats task-specific context blocks for major analysis agents.
- Until an external vector store adapter is approved, non-fake embedding
  providers re-embed SQL chunk text on demand for retrieval. The fake provider
  uses deterministic lexical ranking so tests do not depend on meaningless hash
  vector similarity.
- `AnalysisService` builds semantic agent contexts only after retained seed and
  source documents index successfully, and passes those contexts into
  `run_analysis()` without changing API response shapes.
- Each context block includes semantic chunk/document IDs, SQL source IDs, and
  `S1`/`S2`-style source refs when available. Excerpts are capped so the prompts
  do not receive full article dumps.

Implementation:

- Before `run_analysis()`, build task-specific context blocks with retrieved
  chunks and source IDs.
- Keep the current compact source manifest, but enrich it with retrieved chunks.
- Avoid dumping full articles into every prompt.

Suggested retrieval targets:

- Fact extractor: direct factual claims, procedural details, official quotes,
  legal sections, observable visual evidence.
- Rhetorical analyst: headline/subheadline chunks, loaded language passages,
  opinion sections, attributed political claims.
- Narrative analyzer: chunks grouped by bias bucket, side-specific emphasis,
  omissions, counter-narrative passages.
- Report writer: structured claims, coverage snapshot, source matrix data,
  citation-ready chunks, visual observations.

Done when:

- Each major analysis task receives source-linked chunks relevant to its job,
  not only a generic excerpt or previous-agent prose.

### Phase 7: Agent Finding and Visual Evidence Memory

Goal: preserve structured findings as searchable memory.

Current implementation choice:

- `SemanticMemoryService` supports first-class `visual_evidence` documents with
  observable text, visible symbols/numbers, observable objects, reported context,
  interpretation, and legal characterization preserved as separate metadata and
  text sections.
- `SemanticMemoryService.index_structured_finding()` stores typed finding
  documents for `fact_claims`, `rhetoric_findings`, `narrative_findings`, and
  `coverage_asymmetry`, while retaining story, analysis, and source-reference
  metadata.
- `AnalysisService` indexes visual evidence before semantic agent-context
  retrieval so fact/report prompts can retrieve observable media records during
  the same run.
- `AnalysisService` indexes structured report-section findings after the
  persisted `Analysis` row exists. The current CrewAI flow still returns after
  all tasks complete, so these findings are available for later retrieval,
  rebuilds, and follow-up runs rather than mid-run task-to-task retrieval.
- Phase 7 remains fail-open under the existing semantic memory guardrails.

Implementation:

- Store structured findings after structured report sections are produced.
- Embed source-grounded findings when `SEMANTIC_MEMORY_ENABLED=true`.
- Index `VisualEvidenceRecord` text as a separate semantic document type.
- Keep visual evidence separated into:
  - observable content
  - reported context
  - interpretation
  - legal characterization

Done when:

- Later agents can retrieve prior findings by meaning and source linkage.
- Reports separate what is visible in media from what sources claim it means.

## Testing Plan

### Unit Tests

Add focused tests for:

- semantic query expansion disabled by default
- semantic query expansion fail-open behavior
- query JSON validation and dedupe
- chunking boundaries and overlap
- metadata validation
- fake embedding provider
- vector store adapter write/read/search/delete
- seed story indexing
- retained source indexing
- agent finding indexing
- rebuild story index

### Relevance Fixtures

Create fixtures for:

- same event, different wording = accepted
- same person, different event = rejected
- same topic, wrong date = rejected or contextual
- semantically similar but missing distinctive token = contextual, not direct
- opposing-side article with different framing = accepted if same event

### Bias-Balance Fixtures

Create a candidate pool with:

- five left-side articles
- one center article
- one right-side article using different wording

Expected:

- retained sources include required left/right coverage when discoverable
- exact-bias and bucket caps still apply
- strict bucket enforcement still fails when a required side is truly missing

### Agent Memory Fixtures

Create a fake story with:

- three source article chunks
- two structured agent findings
- one visual evidence record

Expected:

- fact/rhetoric/narrative/report contexts retrieve different relevant chunks
- retrieved chunks include `source_id` and `semantic_chunk_id`

## Failure Behavior

Semantic memory must not make the app brittle.

If semantic query expansion fails:

- log warning
- keep deterministic `query_pack`
- continue analysis

If vector indexing fails:

- log warning/error with provider, model, and story/source context
- mark semantic diagnostics unavailable
- continue deterministic scoring when `SEMANTIC_FAIL_OPEN=true`

If one candidate embedding fails:

- set `semantic_similarity=None`
- continue deterministic scoring

If semantic retrieval returns irrelevant chunks:

- deterministic filters, must-have terms, must-not-have terms, and coverage type
  still decide direct coverage eligibility

## Acceptable Final Result For Future Implementation

The semantic implementation is acceptable when all of these are true:

1. Semantic query expansion improves RSS/search recall and is disabled by
   default until configured.
2. No new CrewAI agent is added for query expansion.
3. SQL remains the source of truth for stories, sources, analyses, semantic
   documents, and semantic chunks.
4. The vector DB can be deleted and rebuilt from SQL semantic chunk rows.
5. Vector records include metadata linking back to SQL records.
6. Same-event/different-wording coverage is accepted by tests.
7. Same-person/wrong-event coverage is rejected or downgraded by tests.
8. Distinctive event markers, must-have terms, must-not-have terms, and direct
   coverage classification still gate source acceptance.
9. Bias-balanced source selection still controls the final retained source set.
10. Semantic failures fail open in development and surface diagnostics.
11. Agent contexts include source-linked retrieved chunks, not only summaries.
12. Visual evidence memory keeps observable content separate from interpretation.
13. The Codex OAuth limitation is respected: chat expansion may use the bridge,
    embeddings may not unless a real embeddings endpoint is added.

## Sources Consulted

- OpenAI embeddings guide:
  https://platform.openai.com/docs/guides/embeddings
- OpenAI `text-embedding-3-large` model page:
  https://platform.openai.com/docs/models/text-embedding-3-large
- LiteLLM embeddings docs:
  https://docs.litellm.ai/docs/embedding/supported_embedding
- LanceDB quickstart:
  https://docs.lancedb.com/quickstart
- LanceDB metadata filtering:
  https://docs.lancedb.com/search/filtering
- Chroma clients:
  https://docs.trychroma.com/docs/run-chroma/clients
- Chroma metadata filtering:
  https://docs.trychroma.com/docs/querying-collections/metadata-filtering
- Sentence Transformers docs:
  https://sbert.net/
