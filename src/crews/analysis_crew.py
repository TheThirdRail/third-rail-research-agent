"""Analysis Crew for multi-source story research."""

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


def create_analysis_tasks(
    story_description: str,
    story_url: str | None = None,
    prefetched_sources: str | None = None,
) -> list[Task]:
    """Create tasks for the analysis workflow.

    Args:
        story_description: Description of the story to analyze
        story_url: Optional URL of a source article
        prefetched_sources: Optional prefetched source context block

    Returns:
        List of CrewAI tasks
    """
    source_context = (
        f"Starting URL: {story_url}" if story_url else "No starting URL provided."
    )
    prefetched_context = (
        f"\n\nPrefetched Sources:\n{prefetched_sources}\n"
        if prefetched_sources
        else ""
    )
    rhetoric_rubric = build_rhetoric_rubric()

    # Task 1: Find all sources covering this story
    source_task = Task(
        description=f"""Find all available news sources covering this story:

        Story: {story_description}
        {source_context}
        {prefetched_context}

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
        agent=create_source_aggregator_agent(),
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
        description="""Analyze the articles to separate facts from opinions.

        For each source:
        1. Identify verifiable facts (who, what, when, where)
        2. Identify editorial opinions and interpretations
        3. Note which facts appear in multiple sources
        4. Note which facts only appear in left-leaning or right-leaning sources

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

        Use ONLY the source manifest from the previous tasks. Do not add new sources.

        The report should include:
        1. Executive Summary (3-5 sentences)
        2. Story Overview (what happened, key players) - 2-3 short paragraphs
        3. Source Matrix (all sources with bias ratings) as a Markdown table
        4. Agreed Facts (confirmed across sources)
        5. Disputed Facts (reported differently by sides)
        6. Opinion Analysis (what each side is saying)
        7. Framing & Context Omissions
        8. Logical Fallacies
        9. Linguistic Manipulation & Dog Whistles
        10. Fact vs Opinion Ambiguities
        11. Narrative Analysis:
           - Mainstream media narrative
           - Alternative/independent takes
           - Libertarian perspective angle
        12. Recommended Approach (for a libertarian creator)
        13. Video Outline (bullet points for video structure)
        14. All Sources & Citations (footnotes)

        Section routing rules:
        - Place findings in the most relevant section above when possible.
        - If a finding does not cleanly fit an existing section, create:
          "Additional Rhetorical Signals"
        - If no high-confidence manipulation/fallacy findings exist, state that clearly.

        Formatting requirements:
        - Use Markdown headings and bullet lists.
        - The Source Matrix MUST be a Markdown table with this schema:
          | Source | Domain | URL | Bias (score+label) | Confidence | Key Framing / Claim |
        - The Source cell MUST include source numbering like:
          S1 [Headline text](https://example.com/article)
        - The Source column MUST be a Markdown link using the headline text:
          [Headline text](https://example.com/article)
        - Every factual or opinionated statement must include a citation marker
          using GFM footnotes, e.g. "The governor vetoed the bill[^3]."
        - Every claim in Framing, Fallacies, Manipulation/Dog Whistles, and
          Fact vs Opinion Ambiguities MUST include citation markers ([^n]).
        - Citation markers MUST map to preflighted source URLs only.
        - The "All Sources & Citations" section MUST list footnotes like:
          [^1]: Source Name — https://example.com/article
        - Provide moderate verbosity (add detail, but avoid excessive length).
        - Ensure citations correspond to the sources referenced.

        Format as clean Markdown with clear sections.""",
        expected_output="A comprehensive Markdown report with all sections.",
        agent=create_report_writer_agent(),
        context=[source_task, bias_task, fact_task, rhetoric_task, narrative_task],
    )

    return [source_task, bias_task, fact_task, rhetoric_task, narrative_task, report_task]


def run_analysis(
    story_description: str,
    story_url: str | None = None,
    prefetched_sources: str | None = None,
) -> dict:
    """Run the full analysis workflow.

    Args:
        story_description: Description of the story
        story_url: Optional starting URL
        prefetched_sources: Optional prefetched source context block

    Returns:
        Dictionary with analysis results
    """
    tasks = create_analysis_tasks(story_description, story_url, prefetched_sources)

    crew = Crew(
        agents=[
            create_source_aggregator_agent(),
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

    return {
        "report": str(result),
        "story_description": story_description,
        "story_url": story_url,
    }
