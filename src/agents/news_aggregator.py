"""News Aggregator Agent for story discovery."""

from crewai import Agent

from src.agents.config import AGENT_ROLES, get_llm_config
from src.tools import NewsSearchTool, RSSAggregatorTool


def create_news_aggregator_agent() -> Agent:
    """Create the news aggregator agent.

    This agent fetches news from RSS feeds and web search
    to find stories relevant to the channel's topics.
    """
    config = AGENT_ROLES["news_aggregator"]

    return Agent(
        role=config["role"],
        goal=config["goal"],
        backstory=config["backstory"],
        tools=[RSSAggregatorTool(), NewsSearchTool()],
        verbose=True,
        allow_delegation=False,
    )
