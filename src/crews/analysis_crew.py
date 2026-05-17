"""Analysis Crew for multi-source story research."""

from typing import Any

from crewai import Crew, Process, Task

from src.agents import (
    create_bias_classifier_agent,
    create_fact_extractor_agent,
    create_narrative_analyzer_agent,
    create_report_writer_agent,
    create_rhetorical_analyst_agent,
    create_source_aggregator_agent,
)
from src.crews.analysis_rubric import build_rhetoric_rubric
from src.schemas.analysis_report_sections import AnalysisReportSections


def _extract_final_report_payload(result: Any) -> dict[str, Any]:
    """Extract the final task JSON from CrewAI's result object."""
    candidates: list[Any] = []
    for attr in ("json_dict", "pydantic", "raw"):
        value = getattr(result, attr, None)
        if value:
            candidates.append(value)

    tasks_output = getattr(result, "tasks_output", None)
    if tasks_output:
        final_output = tasks_output[-1]
        for attr in ("json_dict", "pydantic", "raw"):
            value = getattr(final_output, attr, None)
            if value:
                candidates.append(value)
        candidates.append(final_output)

    candidates.append(result)

    for candidate in candidates:
        if isinstance(candidate, AnalysisReportSections):
            return candidate.model_dump()
        if hasattr(candidate, "model_dump"):
            dumped = candidate.model_dump()
            if isinstance(dumped, dict):
                return dumped
        if isinstance(candidate, dict):
            return candidate

        text = str(candidate).strip()
        if not text:
            continue
        try:
            sections = AnalysisReportSections.from_crew_payload(
                {"report": text},
            )
        except ValueError:
            continue
        if sections.model_dump(exclude_defaults=True):
            return sections.model_dump()

    return {"report": str(result)}


def _agent_context_block(
    agent_contexts: dict[str, str] | None,
    agent_name: str,
) -> str:
    context = (agent_contexts or {}).get(agent_name, "").strip()
    if not context:
        return ""
    return f"\n\nRetrieved Semantic Context:\n{context}\n"


def create_analysis_tasks(
    story_description: str,
    story_url: str | None = None,
    prefetched_sources: str | None = None,
    visual_evidence_context: str | None = None,
    agent_contexts: dict[str, str] | None = None,
) -> list[Task]:
    """Create tasks for the analysis workflow.

    Args:
        story_description: Description of the story to analyze
        story_url: Optional URL of a source article
        prefetched_sources: Optional prefetched source context block
        agent_contexts: Optional semantic context blocks keyed by agent name

    Returns:
        List of CrewAI tasks
    """
    source_context = (
        f"Starting URL: {story_url}" if story_url else "No starting URL provided."
    )
    prefetched_context = (
        f"\n\nPrefetched Sources:\n{prefetched_sources}\n" if prefetched_sources else ""
    )
    visual_context = (
        f"\n\nObservable Visual Evidence:\n{visual_evidence_context}\n"
        if visual_evidence_context
        else ""
    )
    fact_context = _agent_context_block(agent_contexts, "fact_extractor")
    rhetoric_context = _agent_context_block(agent_contexts, "rhetorical_analyst")
    narrative_context = _agent_context_block(agent_contexts, "narrative_analyzer")
    report_context = _agent_context_block(agent_contexts, "report_writer")
    rhetoric_rubric = build_rhetoric_rubric()
    source_agent = create_source_aggregator_agent(
        prefetched_mode=bool(prefetched_sources)
    )

    # Task 1: Find all sources covering this story
    source_task = Task(
        description=f"""Find all available news sources covering this story:

        Story: {story_description}
        {source_context}
        {prefetched_context}
        {visual_context}

        If prefetched sources are provided, you MUST use ONLY those sources and
        MUST NOT search for additional sources.

        Steps:
        1. Search for news articles about this story
        2. Find sources from left, center, and right-leaning outlets
        3. Include libertarian and independent sources if available
        4. Return concise, source-numbered evidence excerpts only.

        Return a compact source manifest with source IDs, URLs, domains, bias,
        and short evidence excerpts. Do not paste full article text.""",
        expected_output="A compact list of preflighted sources with URLs, domains, bias, and short excerpts.",
        agent=source_agent,
    )

    # Task 2: Classify bias of each source
    bias_task = Task(
        description="""Classify the political bias of each source found.

        For each source:
        1. Look up the domain in the bias database
        2. Assign a bias score from -4 (Far Left) to +4 (Far Right)
        3. Note the confidence level and method used

        Create a summary table of sources sorted by bias.""",
        expected_output="A table of sources with bias scores from -4 to +4.",
        agent=create_bias_classifier_agent(),
        context=[source_task],
    )

    # Task 3: Extract facts vs opinions
    fact_task = Task(
        description=f"""Analyze the articles to separate facts from opinions.

        For each source:
        1. Identify verifiable facts (who, what, when, where)
        2. Identify editorial opinions and interpretations
        3. Note which facts appear in multiple sources
        4. Note which facts only appear in left-leaning or right-leaning sources

        Use the visual evidence context as observable evidence only; do not infer
        intent, legality, or motive from image contents unless a source attributes
        that interpretation.
        {fact_context}

        Create three lists:
        - Agreed facts (appear across perspectives)
        - Left-only facts (only in left-leaning sources)
        - Right-only facts (only in right-leaning sources)""",
        expected_output="Three categorized lists of facts with source attributions.",
        agent=create_fact_extractor_agent(),
        context=[source_task, bias_task],
    )

    # Task 4: Detect rhetoric and manipulation patterns
    rhetoric_task = Task(
        description=f"""Analyze the source texts for rhetoric and manipulation patterns.

        Use this compact rubric:
        {rhetoric_rubric}
        {rhetoric_context}

        Required output schema:
        ### Framing Tactics
        ### Linguistic Manipulation / Loaded Terms
        ### Logical Fallacies
        ### Dog Whistles / Coded Terms (context-gated)
        ### Fact-Opinion Boundary Cases

        For each finding, include all fields:
        - Finding label
        - Evidence snippet or precise paraphrase
        - Why it matches the rubric category
        - Source citation marker(s), e.g. [^2]
        - Confidence: high|medium|low

        Rules:
        - Do not classify by keyword alone; apply context checks.
        - If confidence is low, label as possible signal, not definitive manipulation.
        - If no high-confidence findings exist for a section, write:
          "No high-confidence findings."
        - Use only sources provided in context.""",
        expected_output="Structured rhetoric analysis with citations and confidence per finding.",
        agent=create_rhetorical_analyst_agent(),
        context=[source_task, bias_task, fact_task],
    )

    # Task 5: Narrative analysis
    narrative_task = Task(
        description=f"""Analyze the narrative patterns across all sources for this story:

        Story: {story_description}
        {narrative_context}

        Using the fact extraction and rhetoric analysis above, produce:
        1. **Mainstream Narrative**: The dominant story told by center/mainstream sources.
        2. **Alternative Narrative**: How independent/non-mainstream sources frame it.
        3. **Creator Angles**: 2-3 specific angles a libertarian/independent creator
           could explore, grounded in evidence from the sources.
        4. **Omission Patterns**: What each ideological side omits or underplays.
        5. **Headline Framing Differences**: Notable differences in how outlets
           headline the same event.
        6. **Opinion Clusters**: Group similar opinions by ideological alignment.

        Rules:
        - Every narrative claim must reference source IDs from the source task.
        - If a bias bucket is missing from the source set, note it as a
          missing perspective — do NOT fabricate what that side would say.
        - Separate evidence-derived patterns from creator-angle suggestions.""",
        expected_output="Structured narrative analysis with mainstream/alternative/creator angles.",
        agent=create_narrative_analyzer_agent(),
        context=[source_task, bias_task, fact_task, rhetoric_task],
    )

    # Task 6: Write the final report
    report_task = Task(
        description=f"""Write a comprehensive research report for this story:

        Story: {story_description}
        {report_context}

        Use ONLY the source manifest from the previous tasks. Do not add new sources.

        Return ONLY valid JSON matching this schema:
        {{
          "executive_summary": "3-5 neutral sentences",
          "what_happened": "story-first event narrative",
          "directly_observable": "only directly visible/observable facts",
          "what_is_disputed": "what sources dispute or interpret differently",
          "coverage_snapshot": "brief coverage/bucket summary if available",
          "agreed_facts": "facts confirmed across sources",
          "opinion_analysis": "what each side is saying",
          "framing_omissions": "framing and context omissions",
          "logical_fallacies": "high-confidence fallacy findings or none",
          "linguistic_manipulation": "loaded terms/coded language or none",
          "fact_opinion_ambiguities": "boundary cases",
          "mainstream_narrative": "dominant narrative",
          "alternative_takes": "independent/alternative narrative patterns",
          "creator_angles": ["2-3 evidence-grounded creator angles"],
          "recommended_approach": "creator-facing approach",
          "video_outline": "concise outline",
          "evidence_limitations": ["limitations, missing perspectives, or visual failures"],
          "source_findings": [
            {{
              "source_id": "S1",
              "key_framing": "one concise framing or emphasis used by this source",
              "notable_claim": "one source-specific claim or evidence note",
              "evidence_snippet": "short supporting phrase or paraphrase",
              "confidence": 0.0
            }}
          ]
        }}

        Rules:
        - Do not include Markdown headings.
        - Do not include a Source Matrix or All Sources & Citations.
        - The deterministic renderer will add layout, matrix, and citations.
        - Include one source_findings entry for each provided source ID.
        - Keep observable visual content separate from interpretation and legal characterization.
        - Every substantive claim should reference source IDs like S1/S2 in the text.""",
        expected_output="Valid JSON matching AnalysisReportSections fields; no Markdown headings.",
        agent=create_report_writer_agent(),
        context=[source_task, bias_task, fact_task, rhetoric_task, narrative_task],
    )

    return [
        source_task,
        bias_task,
        fact_task,
        rhetoric_task,
        narrative_task,
        report_task,
    ]


def run_analysis(
    story_description: str,
    story_url: str | None = None,
    prefetched_sources: str | None = None,
    visual_evidence_context: str | None = None,
    agent_contexts: dict[str, str] | None = None,
) -> dict:
    """Run the full analysis workflow.

    Args:
        story_description: Description of the story
        story_url: Optional starting URL
        prefetched_sources: Optional prefetched source context block
        agent_contexts: Optional semantic context blocks keyed by agent name

    Returns:
        Dictionary with analysis results
    """
    tasks = create_analysis_tasks(
        story_description,
        story_url,
        prefetched_sources,
        visual_evidence_context,
        agent_contexts,
    )

    crew = Crew(
        agents=[
            create_source_aggregator_agent(prefetched_mode=bool(prefetched_sources)),
            create_bias_classifier_agent(),
            create_fact_extractor_agent(),
            create_rhetorical_analyst_agent(),
            create_narrative_analyzer_agent(),
            create_report_writer_agent(),
        ],
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
        tracing=False,
    )

    result = crew.kickoff()
    report_payload = _extract_final_report_payload(result)
    sections = AnalysisReportSections.from_crew_payload(
        report_payload,
        fallback_summary=story_description,
    )
    raw_report = (
        report_payload.get("report")
        if isinstance(report_payload.get("report"), str)
        else sections.model_dump_json()
    )

    return {
        "report": raw_report,
        "report_json": report_payload,
        "sections": sections.model_dump(),
        "story_description": story_description,
        "story_url": story_url,
    }
