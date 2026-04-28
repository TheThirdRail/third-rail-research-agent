"""Source Aggregator Agent for multi-source research."""

from crewai import Agent

from src.agents.config import AGENT_ROLES, build_crewai_llm
from src.tools.article_extractor import ArticleExtractorTool
from src.tools.web_search import WebSearchTool


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
        tools=[WebSearchTool(), ArticleExtractorTool()],
        llm=build_crewai_llm(agent_name="source_aggregator"),
        verbose=True,
        allow_delegation=False,
    )
