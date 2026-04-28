"""Rhetorical Analyst Agent for manipulation and fallacy detection."""

from crewai import Agent

from src.agents.config import AGENT_ROLES, build_crewai_llm


def create_rhetorical_analyst_agent() -> Agent:
    """Create the rhetorical analyst agent.

    This agent detects framing tactics, manipulation language, logical
    fallacies, and context-dependent coded rhetoric in source text.
    """
    config = AGENT_ROLES["rhetorical_analyst"]

    return Agent(
        role=config["role"],
        goal=config["goal"],
        backstory=config["backstory"],
        tools=[],  # Reasoning-only; uses provided source context.
        llm=build_crewai_llm(agent_name="rhetorical_analyst"),
        verbose=True,
        allow_delegation=False,
    )
