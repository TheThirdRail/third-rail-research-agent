# Dev Branch Hardening Action Plan

Last updated: 2026-05-01

## Purpose

This plan turns the dev-branch diagnosis into an implementation sequence for the
research pipeline. The goal is to make retrieval fair across ideological buckets,
make same-event detection more robust, persist diagnostics and handoff context,
and render final reports without duplicated model-generated report structure.

The plan is intentionally phased. P0 work fixes correctness and debuggability
problems that block later tuning. P1 adds meaning-aware retrieval and memory.
P2 improves quality, observability, and operating ergonomics after the pipeline
contracts stabilize.

## Current Ground Truth

The branch already has most of the right primitives:

- `BalancedSourcePlanner` builds required and optional bucket plans.
- `SourceAggregatorService` gathers search/RSS results, extracts articles,
  scores relevance, checks duplicates, and applies retention policy.
- `StoryParserService` creates `StoryPacket` query and event metadata.
- `RelevanceScorerService` performs deterministic event relevance scoring.
- `source_scoring.py` ranks candidates with bucket-aware signals.
- `ArticleExtractor` captures text plus image/social metadata.
- `VisualEvidenceService` creates structured visual evidence summaries.
- `AnalysisService` orchestrates parsing, retrieval, CrewAI, rendering, and
  persistence.
- `ReportRenderer` owns the final Markdown layout, Source Matrix, and citations.
- Semantic memory and candidate semantic scoring are already partially present
  in this working tree.

The main remaining issue is orchestration and persistence: candidates can still
lose lifecycle detail, RSS matching is too loose, source findings are not yet
fully persisted as first-class records, and screenshot/social evidence is not
yet resolved into durable artifacts.

## Success Criteria

The hardening work is complete when:

- Retrieval cannot exhaust the global candidate budget on one side before fairly
  probing required opposing buckets.
- The pipeline can proceed with at least one retained `left_side` and one
  retained `right_side` source, with `center` preferred when available.
- Unique exact-bias diversity is preferred after minimum left/right coverage is
  satisfied.
- RSS candidates are matched against story identity, not just any lexical query
  token.
- Same-event/different-wording stories are accepted, while same-person/wrong-event
  matches are rejected or downgraded.
- Every probed candidate has an inspectable lifecycle state and rejection reason.
- Retained sources persist extraction, relevance, source-score, bucket, and media
  diagnostics.
- `source_findings` populate the Source Matrix with non-empty `key_framing` when
  the crew provides it.
- CrewAI final output is parsed from the final structured task payload instead
  of stringifying the full crew result.
- Visual/social-post evidence can be resolved to screenshots/OCR/metadata or a
  structured fallback reason.
- SQL remains the source of truth; vector data is rebuildable from SQL.

## P0: Correctness and Debuggability

### P0.1 Final Report Payload Extraction

Problem:

`run_analysis()` can receive a wrapped CrewAI result object. If the whole object
is converted with `str(result)`, a Markdown transcript or nested report can be
fed back into `AnalysisReportSections`, creating report-inside-report failures.

Implementation:

- Extract the final task output from CrewAI result attributes such as
  `tasks_output[-1].json_dict`, `tasks_output[-1].pydantic`, or
  `tasks_output[-1].raw`.
- Parse structured JSON with `AnalysisReportSections.from_crew_payload()`.
- Preserve `report_json` in the result dictionary.
- Keep deterministic renderer-owned headings out of crew output.

Status:

Implemented in `src/crews/analysis_crew.py` with regression coverage in
`tests/test_analysis_crew_structure.py`.

### P0.2 Source Findings Contract and Source Matrix Population

Problem:

`ReportRenderer.SourceRecord` supports `key_framing`, but the analysis contract
did not reliably carry per-source findings into rendering.

Implementation:

- Add `SourceFinding` schema.
- Add `source_findings` to `AnalysisReportSections`.
- Update the final report task contract to request one source finding per source
  ID.
- Map `source_findings[*].key_framing` and `notable_claim` into
  `SourceRecord`.
- Render those values in the Source Matrix.

Status:

Implemented in `src/schemas/analysis_report_sections.py`,
`src/crews/analysis_crew.py`, `src/services/analysis_service.py`, and
`src/services/report_renderer.py`.

### P0.3 Bucket Round-Robin Search Scheduling

Problem:

The old planned search path flattened all bucket search steps into one result
sequence before preflight. A global `candidate_probe_limit` could then be spent
on same-side candidates before the other required side had a fair probe.

Implementation:

- Extend `BucketSpec` with:
  - `probe_quota`
  - `result_quota`
  - `exact_bias_order`
- Extend `SourcePlan` with:
  - `bucket_probe_sequence`
  - `proceed_minimum_groups`
  - `target_unique_exact_biases`
- Build a seed-aware bucket probe sequence:
  - left seed: right, center, left
  - right seed: left, center, right
  - center/unknown seed: center, left, right
- Split bucket domain probes into exact-bias lanes using each bucket's
  `exact_bias_order`.
- Search planned bucket steps round-robin before candidate preflight.
- Keep existing strict bucket retention policy and exact-bias caps in place.
- Apply each planned bucket's `result_quota` during retained candidate selection,
  while allowing explicit same-bias backfill to satisfy non-strict minimums.

Status:

Implemented in `src/services/balanced_source_planner.py` and
`src/services/source_aggregator_service.py`, with tests in
`tests/test_hardening_services.py` and `tests/test_source_aggregator_service.py`.
Bucket-lane attempts and exhaustion reasons are now included in
`CandidateCensus`, so persisted analysis census JSON can explain lanes that
returned no results or stopped because bucket/global probe limits were reached.

### P0.4 Retrieval Candidate Census

Problem:

The service currently exposes some aggregate counters in memory, but it does not
persist a durable candidate lifecycle census that explains what happened to every
candidate.

Implementation:

- Add retrieval diagnostic schemas for candidate lifecycle decisions.
- Track candidate states:
  - discovered
  - extraction_failed
  - extracted
  - relevance_rejected
  - duplicate_rejected
  - policy_rejected
  - retained
- Represent seed URL extraction under the `primary` discovery stage.
- Capture:
  - URL, domain, title
  - stage: `rss`, `site_search`, `open_web`
  - bucket label and exact bias
  - extraction diagnostics
  - relevance diagnostics
  - source score
  - media diagnostics
  - rejection reason
- Persist candidate rows under an analysis run ID.
- Add a coverage/census summary to the analysis result and diagnostics endpoint.

Status:

Partially complete. `CandidateDecision` and `CandidateCensus` schemas are
present, candidate lifecycle states are tracked during preflight, and
`analysis_runs` / `retrieval_candidates` rows are persisted from
`AnalysisService`. Stored `analyses` rows now include coverage, census, and
visual evidence JSON snapshots. Missing bucket explanations now include a
structured reason, per-state counts, rejection-reason counts, and whether the
candidate probe limit was reached. Legacy SQLite schema-sync coverage now
verifies the diagnostic tables and analysis snapshot columns. Seed URL
extraction now records `primary` lifecycle rows for both retained and failed
primary candidates.

### P0.5 RSS Story Matching Precision

Problem:

RSS matching currently accepts items when any query token appears in title or
summary. That is too broad for recurring names, continuing stories, and
screenshot/social-post stories.

Implementation:

- Add `RssRetrievalService.search_story(packet, bucket_spec, max_results)`.
- Score RSS items with:
  - canonical headline/title overlap
  - actor overlap
  - action-verb overlap
  - distinctive-term overlap
  - date-window overlap
  - quote, number, and platform marker overlap
  - `must_not_have_terms` exclusions
- Add `rss_candidate_min_story_score`.
- Reject summary-only weak matches even if the feed domain is desired.
- Keep the old `search()` method as a compatibility wrapper until callers move.

Status:

Implemented in `src/services/rss_retrieval_service.py` and wired through
`src/services/source_aggregator_service.py`, with regression coverage in
`tests/test_analysis_rss_retrieval.py` and `tests/test_source_aggregator_service.py`.

## P1: Meaning-Aware Retrieval and Memory

### P1.1 StoryPacket Discriminators

Implementation:

- Extend or fill:
  - `aliases`
  - `negative_clues`
  - `must_not_have_terms`
  - `quote_markers`
  - `number_markers`
  - `platform_markers`
  - visual-identifying tokens
  - semantic query pack
- Extract distinctive numbers, quoted phrases, platform names, and social-post
  URLs from description, URL slug, seed article, and RSS fallback metadata.

Status:

Implemented for the deterministic parser path. `StoryPacket` now exposes
aliases, negative clues, must-not-have terms, quote markers, number markers,
platform markers, visual descriptors, and grouped query families. The parser
populates those fields for recurring-name and social/visual stories.

### P1.2 Semantic Query Expansion

Implementation:

- Add or finalize `SemanticQueryExpansionService`.
- Produce:
  - lexical queries
  - semantic paraphrase queries
  - opposing-frame queries
  - visual/social queries
  - negative terms
  - entity aliases
- Keep expansion fail-open and disabled by default unless configured.
- Search by bucket lane and query family rather than one flat query list.

Status:

Implemented for deterministic query families. `SemanticQueryExpansionService`
produces lexical, semantic paraphrase, opposing-frame, and visual/social query
families; `StoryParserService` stores them on `StoryPacket`; and
`SourceAggregatorService` prefers family order while probing bucket lanes. The
optional LLM expander remains fail-open and appends into the semantic
paraphrase family.

### P1.3 Hybrid Relevance Scoring

Implementation:

- Keep deterministic lexical gates authoritative.
- Add semantic components:
  - semantic chunk similarity
  - semantic title/lede similarity
- Return persistable diagnostics, not only a total score.
- Ensure semantic similarity cannot override:
  - must-have failures
  - must-not-have exclusions
  - wrong-event date/entity conflicts
  - missing distinctive markers for direct coverage

Status:

Implemented for the current pre-retention path. Candidate semantic scoring feeds
event similarity, relevance now returns a typed persistable diagnostics object,
source aggregation stores the diagnostics for accepted and rejected candidates,
and deterministic gates ensure semantic similarity cannot override must-have
failures, must-not-have exclusions, or missing distinctive markers. Candidate
semantic scoring now emits title, lede, and chunk similarity diagnostics.
Wrong-event rejections now return explicit reasons such as
`same_person_wrong_event` when the same actor is present but the event marker is
absent.

### P1.4 Semantic Memory and Agent Handoffs

Implementation:

- Use SQL as source of truth.
- Store semantic documents and chunks for:
  - seed story
  - retained source articles
  - visual evidence
  - fact findings
  - rhetoric findings
  - narrative findings
  - coverage asymmetry
- Keep vector records rebuildable from SQL chunk rows.
- Retrieve task-specific chunks before CrewAI tasks.
- Persist handoff bundles for each major stage.

Status:

Implemented for the current structured pipeline. Durable `analysis_runs`,
`semantic_documents`, `semantic_chunks`, `agent_findings`, and `agent_handoffs`
are present. Retained source articles, visual evidence, and structured report
findings are indexed into semantic memory, while the same structured findings
are also persisted as SQL `agent_findings`. `AnalysisService` now records
post-retrieval, pre-crew, and per-agent handoff bundles for fact, rhetoric,
narrative, and report handoff stages.

### P1.5 Social Post Resolver and Screenshot Capture

Implementation:

- Add `SocialPostResolverService.resolve(post_url)`.
- Add `ScreenshotCaptureService.capture(url_or_html)`.
- Support canonicalization for X/Twitter, Instagram, Threads, Facebook, TikTok,
  and Truth Social URLs.
- Attempt metadata/oEmbed where available.
- Fall back to restricted headless browser capture.
- Persist:
  - resolved URL
  - platform
  - render method
  - screenshot artifact path
  - OCR text
  - vision summary
  - capture success
  - fallback reason

Status:

Partially complete. `SocialPostResolverService` canonicalizes X/Twitter,
Instagram, Threads, Facebook, TikTok, and Truth Social URLs and attempts public
oEmbed retrieval where supported. `ScreenshotCaptureService` now returns
structured screenshot provenance, OCR text fields, and fallback reasons without
storing raw screenshot artifacts. `VisualEvidenceService` routes `social_post`
media pointers through the resolver/capture path and persists the resulting
metadata through existing visual evidence JSON/metadata records. Actual
restricted browser capture remains open until a browser dependency/retention
policy is approved.

## P2: Quality, Observability, and Operations

### P2.1 Diagnostics API

Implementation:

- Add `GET /analysis/{story_id}/diagnostics`.
- Return:
  - coverage snapshot
  - candidate lifecycle census
  - missing bucket reasons
  - RSS precision counts
  - extraction failures
  - semantic memory diagnostics
  - visual evidence diagnostics

Status:

Implemented. `GET /analysis/{story_id}/diagnostics` returns persisted coverage,
candidate census, visual evidence, handoff snapshot, latest analysis-run status,
and retrieval candidate lifecycle rows. `GET
/analysis/{story_id}/handoff/{stage}` returns the persisted handoff bundle for a
specific stage.

### P2.2 Handoff API

Implementation:

- Add `GET /analysis/{story_id}/handoff/{stage}`.
- Return persisted structured retrieval and findings for:
  - retrieval
  - pre-crew
  - fact extraction
  - rhetoric
  - narrative
  - report writing

Status:

Implemented. `GET /analysis/{story_id}/handoff/{stage}` returns the persisted
handoff bundle for retrieval, pre-crew, fact, rhetoric, narrative, and report
stages when present.

### P2.3 Reranking and Benchmarking

Implementation:

- Add a benchmark fixture set for recurring-news and screenshot/social stories.
- Measure:
  - opposing-side recall
  - RSS precision
  - wrong-event rejection
  - source matrix completeness
  - semantic retrieval relevance
- Add an optional reranker after baseline retrieval and persistence are stable.

Status:

Not complete.

## Data Model Plan

Add or confirm durable tables:

- `analysis_runs`
- `retrieval_candidates`
- `source_findings` - implemented
- `visual_evidence_records` - implemented
- `semantic_documents` - implemented
- `semantic_chunks` - implemented
- `agent_findings` - implemented
- `agent_handoffs` - implemented

Extend `sources` with:

- `relevance_score` - implemented
- `source_score` - implemented
- `bucket_label` - implemented
- `coverage_type` - implemented
- `extractor_method` - implemented
- `extraction_error` - implemented
- `extraction_error_code` - implemented
- `http_status` - implemented
- `og_image_url` - implemented
- `embedded_post_urls_json` - implemented
- `image_alt_text_json` - implemented
- `media_captions_json` - implemented
- `relevance_diagnostics_json` - implemented
- `media_diagnostics_json` - implemented
- `key_framing` - implemented

Extend `analyses` with:

- `coverage_snapshot_json`
- `candidate_census_json`
- `visual_evidence_json`
- `agent_handoff_snapshot_json`

Migration guidance:

- Prefer a real migration or migration bootstrap over expanding ad hoc startup
  `ALTER TABLE` sync for the entire feature set.
- Keep SQLite-compatible SQL first.
- Add Postgres-specific improvements only after SQLite behavior is stable.

## Embedding and Vector Store Defaults

Recommended default stack:

- Embedding provider: LM Studio OpenAI-compatible `/v1/embeddings`
- Primary model: `Qwen3-Embedding-8B`
- Default quantization for 10 GB RTX 3080: `Q6_K`
- Fallback quantization: `Q5_K_M`
- Vector store: LanceDB
- Optional multimodal model: `Qwen3-VL-Embedding-8B` for screenshot/social-post
  matching only

Operational rules:

- Do not silently fall back from local embeddings to remote APIs.
- Treat vector storage as a rebuildable index.
- Keep source text and chunk text in SQL.
- Keep screenshot/social artifacts configurable and provenance-linked.

## Testing Plan

Required targeted tests:

- bucket round-robin scheduler
- exact-bias lane fill
- RSS story matching precision
- semantic query expansion
- semantic memory chunking
- hybrid relevance scoring
- social-post resolver
- screenshot/visual evidence persistence
- source findings renderer
- analysis handoff retrieval
- SQL migration on fresh and legacy SQLite DBs
- end-to-end balanced probe

Current verified checks from the first P0 pass:

```powershell
python -m ruff check src/services/balanced_source_planner.py src/services/source_aggregator_service.py src/crews/analysis_crew.py src/schemas/analysis_report_sections.py src/services/report_renderer.py src/services/analysis_service.py tests/test_analysis_crew_structure.py tests/test_hardening_services.py tests/test_source_aggregator_service.py
python -m pytest tests/test_analysis_crew_structure.py tests/test_hardening_services.py tests/test_source_aggregator_service.py -q
```

Result: 58 tests passed.

Additional migration verification:

```powershell
python -m ruff check tests/test_migration_free_tier.py
python -m pytest tests/test_migration_free_tier.py -q
python -m ruff check src/services/source_aggregator_service.py tests/test_source_aggregator_service.py
python -m pytest tests/test_source_aggregator_service.py -q
python -m pytest tests/test_hardening_services.py tests/test_source_aggregator_service.py -q
python -m ruff check src/services/source_aggregator_service.py tests/test_source_aggregator_service.py tests/test_end_to_end_analysis.py
python -m pytest tests/test_source_aggregator_service.py tests/test_end_to_end_analysis.py -q
python -m ruff check src/schemas/story_packet.py src/services/story_parser_service.py src/services/rss_retrieval_service.py tests/test_story_parser_and_relevance.py tests/test_analysis_rss_retrieval.py
python -m pytest tests/test_story_parser_and_relevance.py tests/test_analysis_rss_retrieval.py -q
python -m ruff check src/schemas/story_packet.py src/services/story_parser_service.py src/services/semantic_query_expansion_service.py src/services/source_aggregator_service.py src/services/__init__.py tests/test_story_parser_and_relevance.py tests/test_source_aggregator_service.py
python -m pytest tests/test_story_parser_and_relevance.py tests/test_source_aggregator_service.py -q
python -m ruff check src/schemas/retrieval_diagnostics.py src/services/relevance_scorer_service.py src/services/source_aggregator_service.py tests/test_story_parser_and_relevance.py tests/test_source_aggregator_service.py tests/test_end_to_end_analysis.py
python -m pytest tests/test_story_parser_and_relevance.py tests/test_source_aggregator_service.py tests/test_end_to_end_analysis.py -q
python -m ruff check src/services/candidate_semantic_scorer.py src/services/source_aggregator_service.py tests/test_source_aggregator_service.py tests/test_semantic_memory_service.py
python -m pytest tests/test_source_aggregator_service.py tests/test_semantic_memory_service.py -q
```

Result: Ruff passed; 4 migration tests passed; 10 source-aggregator tests passed;
60 hardening/source-aggregator tests passed; 13 source-aggregator/end-to-end tests
passed; 16 story-parser/RSS tests passed; 24 story-parser/source-aggregator tests
passed; 29 story-parser/source-aggregator/end-to-end tests passed; 23
source-aggregator/semantic-memory tests passed.

## Rollout Order

1. Finish P0 output contract and Source Matrix contract.
2. Finish P0 fair probing and candidate lifecycle persistence.
3. Tighten RSS matching using story identity.
4. Expand missing bucket explanations before tuning thresholds.
5. Complete semantic query expansion integration by bucket/query family.
6. Complete hybrid relevance diagnostics persistence.
7. Add schema-backed source findings, visual evidence records, and handoffs.
8. Add social-post resolver and screenshot capture behind a feature flag.
9. Add diagnostics and handoff APIs.
10. Add benchmark harness and reranker only after baseline observability is in.
