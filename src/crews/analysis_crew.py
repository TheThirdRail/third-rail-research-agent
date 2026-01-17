"""Analysis Crew for multi-source story research."""

from crewai import Crew, Process, Task

from src.agents import (
    create_bias_classifier_agent,
    create_fact_extractor_agent,
    create_report_writer_agent,
    create_source_aggregator_agent,
)


def create_analysis_tasks(story_description: str, story_url: str | None = None) -> list[Task]:
    """Create tasks for the analysis workflow.

    Args:
        story_description: Description of the story to analyze
        story_url: Optional URL of a source article

    Returns:
        List of CrewAI tasks
    """
    source_context = f"Starting URL: {story_url}" if story_url else "No starting URL provided."

    # Task 1: Find all sources covering this story
    source_task = Task(
        description=f"""Find all available news sources covering this story:

        Story: {story_description}
        {source_context}

        Steps:
        1. Search for news articles about this story
        2. Find sources from left, center, and right-leaning outlets
        3. Include libertarian and independent sources if available
        4. Extract the full article text from each source

        Return a list of sources with their URLs and domains.""",
        expected_output="A list of 5-15 news sources covering the story with URLs and extracted text.",
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

    # Task 4: Write the final report
    report_task = Task(
        description=f"""Write a comprehensive research report for this story:

        Story: {story_description}

        The report should include:
        1. Executive Summary (3-5 sentences)
        2. Story Overview (what happened, key players)
        3. Source Matrix (all sources with bias ratings)
        4. Agreed Facts (confirmed across sources)
        5. Disputed Facts (reported differently by sides)
        6. Opinion Analysis (what each side is saying)
        7. Narrative Analysis:
           - Mainstream media narrative
           - Alternative/independent takes
           - Libertarian perspective angle
        8. Recommended Approach (for a libertarian creator)
        9. Video Outline (bullet points for video structure)
        10. All Sources & Citations

        Format as clean Markdown with clear sections.""",
        expected_output="A comprehensive Markdown report with all sections.",
        agent=create_report_writer_agent(),
        context=[source_task, bias_task, fact_task],
    )

    return [source_task, bias_task, fact_task, report_task]


def run_analysis(story_description: str, story_url: str | None = None) -> dict:
    """Run the full analysis workflow.

    Args:
        story_description: Description of the story
        story_url: Optional starting URL

    Returns:
        Dictionary with analysis results
    """
    tasks = create_analysis_tasks(story_description, story_url)

    crew = Crew(
        agents=[
            create_source_aggregator_agent(),
            create_bias_classifier_agent(),
            create_fact_extractor_agent(),
            create_report_writer_agent(),
        ],
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
    )

    result = crew.kickoff()

    return {
        "report": str(result),
        "story_description": story_description,
        "story_url": story_url,
    }
