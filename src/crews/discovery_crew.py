"""Discovery Crew for finding relevant stories."""

from crewai import Crew, Process, Task

from src.agents import create_news_aggregator_agent


def create_discovery_tasks(channel_topics: list[str]) -> list[Task]:
    """Create tasks for the discovery workflow.

    Args:
        channel_topics: List of topic keywords from channel profile

    Returns:
        List of CrewAI tasks
    """
    topics_str = ", ".join(channel_topics[:10])

    # Task 1: Aggregate news from RSS feeds
    rss_task = Task(
        description=f"""Fetch recent news from RSS feeds related to these topics: {topics_str}

        Use the RSS News Aggregator tool to:
        1. Fetch stories from the past 24 hours
        2. Focus on categories: center, libertarian, independent
        3. Return up to 20 relevant stories

        Return a list of story titles with their sources and URLs.""",
        expected_output="A list of 10-20 news stories with titles, sources, and URLs.",
        agent=create_news_aggregator_agent(),
    )

    # Task 2: Search for additional stories
    search_task = Task(
        description=f"""Search for additional news stories on these topics: {topics_str}

        Use the News Search tool to:
        1. Search for news from the past week
        2. Find stories not already in the RSS results
        3. Look for trending or breaking news

        Return additional stories with sources and URLs.""",
        expected_output="A list of 5-10 additional news stories from web search.",
        agent=create_news_aggregator_agent(),
    )

    return [rss_task, search_task]


def run_discovery(channel_topics: list[str]) -> dict:
    """Run the discovery workflow.

    Args:
        channel_topics: List of topic keywords

    Returns:
        Dictionary with discovered stories
    """
    tasks = create_discovery_tasks(channel_topics)

    crew = Crew(
        agents=[create_news_aggregator_agent()],
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
    )

    result = crew.kickoff()

    return {
        "raw_output": str(result),
        "topics_searched": channel_topics,
    }
