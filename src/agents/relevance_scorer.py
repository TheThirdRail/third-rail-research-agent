"""Relevance Scorer Agent for ranking stories."""

from crewai import Agent

from src.agents.config import AGENT_ROLES, build_crewai_llm


def create_relevance_scorer_agent() -> Agent:
    """Create the relevance scorer agent.

    This agent ranks stories by relevance to the channel's
    focus areas and predicted audience interest.
    """
    config = AGENT_ROLES["relevance_scorer"]

    return Agent(
        role=config["role"],
        goal=config["goal"],
        backstory=config["backstory"],
        tools=[],  # Uses LLM reasoning for scoring
        llm=build_crewai_llm(agent_name="relevance_scorer"),
        verbose=True,
        allow_delegation=False,
    )
