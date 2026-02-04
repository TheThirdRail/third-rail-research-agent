"""Relevance Scorer Agent for ranking stories."""

from crewai import Agent

from src.agents.config import AGENT_ROLES, get_llm_config


def create_relevance_scorer_agent() -> Agent:
    """Create the relevance scorer agent.

    This agent ranks stories by relevance to the channel's
    focus areas and predicted audience interest.
    """
    config = AGENT_ROLES["relevance_scorer"]
    llm_config = get_llm_config(agent_name="relevance_scorer")

    return Agent(
        role=config["role"],
        goal=config["goal"],
        backstory=config["backstory"],
        tools=[],  # Uses LLM reasoning for scoring
        llm=llm_config.get("model"),
        verbose=True,
        allow_delegation=False,
    )
