# Model Lock-In — Deferred Configuration

**Status:** Deferred  
**Reason:** Not locking in model assignments until the architecture is stabilized.

---

## Recommended Target Model Settings (for future reference)

These recommendations come from the `things-to-fix.md` analysis and are parked here until the architectural changes below are complete and evaluated.

| Component | Model | Thinking | Temperature | Rationale |
|---|---|---:|---:|---|
| `profile_reader` | `gpt-5.4-mini` | Low | 0.2 | Parsing and normalization, mostly bounded |
| `news_aggregator` | `gpt-5.4-mini` initially, `gpt-5.4` if evals require | Low | 0.3 | Discovery is support work once balancing is moved into code |
| `relevance_scorer` | `gpt-5.4-mini` | Low | 0.1 | Stable ranking and rejection behavior |
| `story_parser` | `gpt-5.4` | Medium | 0.2 | Ambiguity resolution and query construction |
| `source_aggregator` | `gpt-5.4` | Medium | 0.2 | Tool-heavy, search-aware, but should be policy-constrained |
| `bias_classifier` | `gpt-5.4` | Low | 0.1 | Stable classification; low randomness |
| `fact_extractor` | `gpt-5.5` | High | 0.1 | Highest truth-discipline requirement |
| `rhetorical_analyst` | `gpt-5.5` | High | 0.2 | Difficult interpretive labeling with high false-positive cost |
| `narrative_analyzer` | `gpt-5.5` | High | 0.4 | Profile-aware synthesis still grounded in evidence |
| `report_writer` | `gpt-5.5` | High | 0.2–0.3 | Final user-facing synthesis, should write from structured inputs |

## Key Principles

- **Move balancing into deterministic code** — then `news_aggregator` can stay on a smaller model.
- **Classification tasks** (bias, relevance) should use low temperature for run-to-run stability.
- **Synthesis tasks** (narrative, report) can use slightly higher temperature for flexibility, but still grounded.
- **Do not use flagship models to compensate for missing hard rules** — fix the rules first.

## When to Revisit

Once the following are complete:
1. Source registry is canonical and drives runtime
2. Balanced source planner enforces bucket policy
3. Story parser and relevance scorer are active pipeline stages
4. Narrative analyzer separates evidence-derived from creator-angle content
5. Report renderer is deterministic (not model-generated tables/footnotes)

Then run evals per-agent and lock in model assignments based on measured quality.
