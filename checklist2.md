# Research Agent Hardening — Checklist 2

**Created:** April 28, 2026  
**Reference:** [implementation_plan.md](file:///C:/Users/jerem/.gemini/antigravity/brain/95d787dd-8e72-4ddb-8eb5-a144f9fe9854/implementation_plan.md) | [things-to-fix.md](file:///d:/Coding/Research-Agent/things-to-fix.md)  
**Model decisions:** Deferred → [model-lock-in.md](file:///d:/Coding/Research-Agent/model-lock-in.md)

---

## P0 — Critical Path

### 1. Canonical Source Registry
- [x] Create `config/source_registry.yaml` merging bias_sources + rss_feeds data
- [x] Create `src/services/source_registry.py` — SourceRegistry class
- [x] Create `scripts/generate_source_docs.py` — generate markdown from registry
- [x] Rewire `LocalBiasDatabase` to read from registry
- [x] Rewire `RSSAggregator._load_feeds()` to read from registry
- [x] Add 30+ additional outlets from `Deep-RSS-Research.md` to registry (76 total)

### 2. Balanced Source Planner & Bucket Policy
- [x] Create `src/services/balanced_source_planner.py` — BalancedSourcePlanner
- [x] Create `src/services/source_scoring.py` — multi-factor scoring
- [x] Create `src/services/duplicate_detector.py` — dedup + syndication detection
- [x] Refactor `source_aggregator_service.py`:
  - [x] Split config into probe_limit / final_min / final_max / required_bucket_policy
  - [x] Replace `_bias_spread_met()` with explicit 3-bucket coverage rules
  - [x] Add quality-aware stopping conditions
  - [x] Return structured status (coverage_satisfied, missing_buckets, etc.)
  - [x] Surface structured warnings for missing buckets
- [x] Fix `rss_aggregator.py` keyword+category bug
- [x] Add config settings: `candidate_probe_limit`, `retained_source_min/max`, `search_time_window_days`, `strict_bucket_enforcement`

### 3. Unified Bias Resolution
- [x] Route `BiasClassifierTool._run()` through `BiasResolutionService`
- [x] Remove dead-end `Unknown` return path from `BiasClassifier.classify()`
- [x] Add rich metadata to every result (confidence, method, provenance, is_curated, etc.)
- [x] Add `Source` model columns: `bias_provenance`, `is_curated_source`, `bias_category`
- [x] Log resolution method for every source

### 4. Deterministic Report Rendering
- [x] Create `src/services/report_renderer.py` — ReportRenderer class
- [x] Build deterministic Source Matrix from Source rows
- [x] Build deterministic footnote block
- [x] Auto-generate Evidence Limits section when buckets missing
- [x] Separate evidence-derived sections from creator-angle sections
- [x] Add validator rules: missing-bucket banner, orphaned citations

---

## P1 — Pipeline Stages

### 5. Story Parser
- [x] Create `src/schemas/story_packet.py` — StoryPacket Pydantic model
- [x] Create `src/services/story_parser_service.py` — StoryParserService
- [x] Add `Story.parsed_metadata` column

### 6. Relevance Scorer
- [x] Create `src/services/relevance_scorer_service.py` — RelevanceScorerService
- [x] Implement multi-factor scoring (entity, event, time, place, topic, novelty)
- [x] Add explicit rejection reasons

### 7. Structured Fact Extraction
- [x] Create `src/schemas/claims.py` — Claim, CoverageAsymmetry, FactExtractionResult

### 8. Narrative Analyzer
- [x] Create `src/schemas/narrative.py` — NarrativeResult Pydantic model
- [x] Create `src/services/narrative_analyzer_service.py`
- [x] Create `src/agents/narrative_analyzer.py`
- [x] Add narrative analysis task to analysis_crew between rhetoric and report
- [x] Wire `create_narrative_analyzer_agent()` into crew
- [x] Export from `src/agents/__init__.py`

### 9. Channel Profile Enhancements
- [x] Add `ChannelProfile` columns: `owner_user_id`, `raw_content`, `format`, `parsed_json`, `version`

---

## P2 — Quality & Polish

### 10. Expanded Rhetoric Rubric
- [x] Add 12 new rhetoric categories to `LINGUISTIC_MANIPULATION_MARKERS`
- [x] Add 7 new fallacies to `LOGICAL_FALLACY_PATTERNS`
- [x] Add two-context evidence requirement for coded-language calls
- [x] Add outlet-voice vs quoted-voice distinction

### 11. Prompt / Service Contract Alignment
- [x] Align analysis_crew prompts with actual service config values
- [x] Reference config names in prompts (probe_limit, retained_min/max, etc.)

### 12. Search Window Tightening
- [x] Default ±7 days for event-based stories (`search_time_window_days`)

---

## Verification Results

### Import Checks (all ✅)
- [x] `src.schemas` — StoryPacket, Claim, FactExtractionResult, NarrativeResult
- [x] `src.services.source_registry` — 76 outlets loaded
- [x] `src.services.balanced_source_planner` — correct bucket generation
- [x] `src.services.duplicate_detector` — same-domain detection
- [x] `src.services.source_scoring` — multi-factor scoring
- [x] `src.services.story_parser_service` — entity/verb/query extraction
- [x] `src.services.report_renderer` — imports OK
- [x] `src.services.narrative_analyzer_service` — imports OK
- [x] `src.tools.bias_classifier` — routes through registry (source=source_registry)
- [x] `src.tools.rss_aggregator` — loads 68 feeds from registry
- [x] `src.database.models` — all new columns compile
- [x] `src.crews.analysis_crew` — 6 tasks with narrative analyzer
- [x] `src.services.report_validator` — new rules: evidence_limits, orphaned_citations

### Functional Checks (all ✅)
- [x] Planner: far-left seed → requires [center, right_side]
- [x] Planner: far-right seed → requires [center, left_side]
- [x] Planner: center seed → requires [left_side, center, right_side]
- [x] Bias classifier: `foxnews.com` → bias=3, Right, source=source_registry
- [x] Story parser: multi-word entities extracted ("President Joe Biden")
- [x] Duplicate detector: same-domain correctly flagged as duplicate

---

## Remaining — Integration (Next Session)

### Not Yet Wired
- [x] Insert StoryParserService into `AnalysisService.analyze()` pipeline
- [ ] Insert RelevanceScorerService into `SourceAggregatorService.gather_sources()`
- [ ] Wire BalancedSourcePlanner into `SourceAggregatorService.gather_sources()`
- [x] Wire ReportRenderer as post-processor in `AnalysisService`
- [x] Add DB migration for new columns (using SQLite migration script)
- [x] Add unit tests for all new services
- [ ] Integration test: end-to-end with seed URL → deterministic report

---

## Legend

| Symbol | Meaning |
|--------|---------|
| `[ ]`  | Not started |
| `[/]`  | In progress |
| `[x]`  | Complete |
