"""Discovery Crew for finding relevant stories."""

from crewai import Agent, Crew, Process, Task

from src.agents import create_news_aggregator_agent


def create_discovery_tasks(
    channel_topics: list[str],
    count: int = 10,
    prefetched_context: str | None = None,
    news_agent: Agent | None = None,
) -> list[Task]:
    """Create tasks for the discovery workflow.

    Args:
        channel_topics: List of topic keywords from channel profile

    Returns:
        List of CrewAI tasks
    """
    topics_str = ", ".join(channel_topics[:10])
    prefetched_block = (
        f"\n\nPrefetched Discovery Context:\n{prefetched_context}\n"
        if prefetched_context
        else ""
    )

    max_count = max(1, count)
    news_agent = news_agent or create_news_aggregator_agent()

    # Task 1: Aggregate news from RSS feeds
    rss_task = Task(
        description=f"""Fetch recent news from RSS feeds related to these topics: {topics_str}
        {prefetched_block}

        Use the RSS News Aggregator tool to:
        1. Fetch stories from the past 24 hours
        2. Focus on categories: center, libertarian, independent, fringe_conspiracy, religion_spiritual, supernatural
        3. Return up to {max_count} relevant stories

        If prefetched context is provided, prioritize those URLs and only supplement missing gaps.

        Return a list of story titles with their sources and URLs.""",
        expected_output=f"A list of up to {max_count} news stories with titles, sources, and URLs.",
        agent=news_agent,
    )

    # Task 2: Search for additional stories
    search_task = Task(
        description=f"""Search for additional news stories on these topics: {topics_str}
        {prefetched_block}

        Use the News Search tool to:
        1. Search for news from the past week
        2. Find stories not already in the RSS results
        3. Look for trending or breaking news
        4. If results lack RSS coverage, use the Article Extractor tool to pull details

        If prefetched context exists, use it as primary evidence and add only genuinely new stories.

        Return additional stories with sources and URLs. Keep the total to roughly {max_count}.""",
        expected_output=f"Additional news stories so the combined output is around {max_count}.",
        agent=news_agent,
    )

    return [rss_task, search_task]


def run_discovery(
    channel_topics: list[str],
    count: int = 10,
    prefetched_context: str | None = None,
) -> dict[str, object]:
    """Run the discovery workflow.

    Args:
        channel_topics: List of topic keywords

    Returns:
        Dictionary with discovered stories
    """
    news_agent = create_news_aggregator_agent()
    tasks = create_discovery_tasks(
        channel_topics,
        count=count,
        prefetched_context=prefetched_context,
        news_agent=news_agent,
    )

    crew = Crew(
        agents=[news_agent],
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
        tracing=False,
    )

    result = crew.kickoff()

    return {
        "raw_output": str(result),
        "topics_searched": channel_topics,
        "prefetched_context": prefetched_context or "",
    }
