# Model Lock-In — Ready for Evaluation

**Status:** Ready for Evaluation  
**Date:** May 5, 2026  
**Reason:** Architectural prerequisites from Hardening Phase P2 are complete. Balanced source planning and deterministic evidence gathering are now in place.

---

## Recommended Target Model Settings

Based on current hardening, these models are recommended for evaluation in the benchmark harness.

| Component | Model | Thinking | Temperature | Rationale |
|---|---|---:|---:|---|
| `profile_reader` | `gpt-4o-mini` | Low | 0.2 | Parsing and normalization |
| `news_aggregator` | `gpt-4o-mini` | Low | 0.3 | Support work; balancing is now in code |
| `relevance_scorer` | `gpt-4o-mini` | Low | 0.1 | Stable ranking and rejection |
| `story_parser` | `gpt-4o` | Medium | 0.2 | Ambiguity resolution and query construction |
| `source_aggregator` | `gpt-4o` | Medium | 0.2 | Tool-heavy; policy-constrained |
| `bias_classifier` | `gpt-4o` | Low | 0.1 | Stable classification |
| `fact_extractor` | `gpt-4o` | High | 0.1 | Truth-discipline requirement |
| `rhetorical_analyst` | `gpt-4o` | High | 0.2 | Interpretive labeling |
| `narrative_analyzer` | `gpt-4o` | High | 0.4 | Evidence-grounded synthesis |
| `report_writer` | `gpt-4o` | High | 0.2–0.3 | User-facing synthesis |

## Architectural Completion Status

The following prerequisites are now **Complete**:
1. **Source Registry**: Canonical and drives runtime.
2. **Balanced Source Planner**: Enforces bucket policy round-robin.
3. **Diagnostics**: Active pipeline stages for story parsing and relevance scoring.
4. **Evidence Layering**: Narrative analyzer separates evidence-derived from creator-angle content.
5. **Deterministic Rendering**: Report renderer handles structured output.

## Next Steps

1. Run the `research-agent benchmark` suite using these model assignments.
2. Compare results against the `baseline.json`.
3. Lock in model IDs in `config/models.yaml` once quality thresholds are verified.
