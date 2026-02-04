"""News Aggregator Agent for story discovery."""

from crewai import Agent

from src.agents.config import AGENT_ROLES, get_llm_config
from src.tools.rss_aggregator import RSSAggregatorTool
from src.tools.web_search import WebSearchTool


def create_news_aggregator_agent() -> Agent:
    """Create the news aggregator agent.

    This agent fetches news from RSS feeds and web search
    to find stories relevant to the channel's topics.
    """
    config = AGENT_ROLES["news_aggregator"]
    llm_config = get_llm_config(agent_name="news_aggregator")

    return Agent(
        role=config["role"],
        goal=config["goal"],
        backstory=config["backstory"],
        tools=[RSSAggregatorTool(), WebSearchTool()],
        llm=llm_config.get("model"),
        verbose=True,
        allow_delegation=False,
    )
