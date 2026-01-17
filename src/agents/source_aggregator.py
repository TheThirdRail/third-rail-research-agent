"""Source Aggregator Agent for multi-source research."""

from crewai import Agent

from src.agents.config import AGENT_ROLES, get_llm_config
from src.tools import (
    ArticleExtractorTool,
    MultiArticleExtractorTool,
    NewsSearchTool,
    WebSearchTool,
)


def create_source_aggregator_agent() -> Agent:
    """Create the source aggregator agent.

    This agent finds and extracts all available sources
    covering a story from across the political spectrum.
    """
    config = AGENT_ROLES["source_aggregator"]

    return Agent(
        role=config["role"],
        goal=config["goal"],
        backstory=config["backstory"],
        tools=[
            NewsSearchTool(),
            WebSearchTool(),
            ArticleExtractorTool(),
            MultiArticleExtractorTool(),
        ],
        verbose=True,
        allow_delegation=False,
    )
