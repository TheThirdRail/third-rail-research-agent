"""Fact Extractor Agent for separating facts from opinions."""

from crewai import Agent

from src.agents.config import AGENT_ROLES, get_llm_config


def create_fact_extractor_agent() -> Agent:
    """Create the fact extractor agent.

    This agent analyzes article text to separate
    verifiable facts from editorial opinions.
    """
    config = AGENT_ROLES["fact_extractor"]

    return Agent(
        role=config["role"],
        goal=config["goal"],
        backstory=config["backstory"],
        tools=[],  # Uses LLM reasoning, no external tools
        verbose=True,
        allow_delegation=False,
    )
