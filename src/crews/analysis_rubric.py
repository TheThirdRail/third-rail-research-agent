"""Concise rhetoric-analysis rubric for analysis crew prompts.

This module intentionally keeps guidance compact to control token usage.
"""

FACT_VS_OPINION_MARKERS = """
Fact vs Opinion markers:
- Fact-like: specific entities, dates, quantities, direct attributions, observable events.
- Opinion-like: evaluative adjectives, prescriptive modals (should/must/ought), moral judgments.
- Hedge/speculation: may/might/seems/suggests/probably/possibly.
- Boundary rule: "X said Y" can be factual about speech even when Y is opinion.
"""

LINGUISTIC_MANIPULATION_MARKERS = """
Linguistic manipulation markers:
- Loaded language and high-emotion labels replacing neutral terms.
- Euphemism/dysphemism or passive voice hiding agency ("mistakes were made").
- Bandwagon cues ("everyone knows"), glittering generalities, empty virtue-word clusters.
- Presupposition traps that smuggle disputed assumptions as given.
"""

LOGICAL_FALLACY_PATTERNS = """
Logical fallacy patterns:
- Ad hominem, straw man, false dichotomy, slippery slope, red herring, whataboutism.
- Motte-and-bailey, equivocation, circular reasoning, no true Scotsman, Texas sharpshooter.
- Distinguish disagreement from fallacy: flag only when argument structure matches.
"""

MEDIA_FRAMING_PATTERNS = """
Media framing patterns:
- Context omission or truncated causality (missing antecedent events).
- Headline/body mismatch and selective sourcing imbalance.
- Episodic framing that obscures systemic context; conflict/"horse race" framing over substance.
- Separate framing choice from factual falsity; framing can bias without explicit false claims.
"""

DOG_WHISTLE_CONTEXT_RULES = """
Dog whistle and coded-term context rules:
- Context-gated analysis only; do not classify by keyword alone.
- Distinguish literal/policy usage from coded in-group signaling.
- Flag as "possible coded signal" when confidence is low or context is ambiguous.
- Apply symmetry checks across ideological directions; avoid one-sided enforcement.
"""

EVIDENCE_AND_CONFIDENCE_RULES = """
Evidence and confidence rules:
- No claim without quote/paraphrase evidence and source marker ([^n]).
- Include brief rationale linking evidence to the taxonomy category.
- Label confidence as high/medium/low for each finding.
- If uncertain, classify as "possible signal" rather than definitive manipulation.
- If no high-confidence findings exist, state "No high-confidence findings."
"""

MICRO_EXAMPLES = """
Micro-examples:
1) "The policy is evil and should be repealed immediately." -> Opinion + loaded language.
2) "Officials said the bill passed 51-49 on Tuesday." -> Factual claim with attribution.
3) "You're either with this bill or against freedom." -> False dichotomy.
"""


def build_rhetoric_rubric() -> str:
    """Build compact rubric text for prompt injection."""
    return "\n\n".join(
        [
            FACT_VS_OPINION_MARKERS.strip(),
            LINGUISTIC_MANIPULATION_MARKERS.strip(),
            LOGICAL_FALLACY_PATTERNS.strip(),
            MEDIA_FRAMING_PATTERNS.strip(),
            DOG_WHISTLE_CONTEXT_RULES.strip(),
            EVIDENCE_AND_CONFIDENCE_RULES.strip(),
            MICRO_EXAMPLES.strip(),
        ]
    )
