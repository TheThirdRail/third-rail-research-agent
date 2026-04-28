"""News Aggregator Agent for story discovery."""

from crewai import Agent

from src.agents.config import AGENT_ROLES, build_crewai_llm
from src.tools.article_extractor import ArticleExtractorTool
from src.tools.rss_aggregator import RSSAggregatorTool
from src.tools.web_search import WebSearchTool


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
        tools=[RSSAggregatorTool(), WebSearchTool(), ArticleExtractorTool()],
        llm=build_crewai_llm(agent_name="news_aggregator"),
        verbose=True,
        allow_delegation=False,
    )
