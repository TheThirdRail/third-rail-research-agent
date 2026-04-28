"""Fact Extractor Agent for separating facts from opinions."""

from crewai import Agent

from src.agents.config import AGENT_ROLES, build_crewai_llm


def create_fact_extractor_agent() -> Agent:
    """Create the fact extractor agent.

    This agent analyzes article text to separate
    verifiable facts from editorial opinions.
    Uses the analysis LLM for higher quality reasoning.
    """
    config = AGENT_ROLES["fact_extractor"]

    return Agent(
        role=config["role"],
        goal=config["goal"],
        backstory=config["backstory"],
        tools=[],  # Uses LLM reasoning, no external tools
        llm=build_crewai_llm(agent_name="fact_extractor"),
        verbose=True,
        allow_delegation=False,
    )
