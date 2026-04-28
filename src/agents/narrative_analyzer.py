"""Narrative Analyzer agent factory."""

from crewai import Agent

from src.agents.config import AGENT_ROLES, build_crewai_llm


def create_narrative_analyzer_agent() -> Agent:
    """Create a narrative analysis agent."""
    role_config = AGENT_ROLES["narrative_analyzer"]
    return Agent(
        role=role_config["role"],
        goal=role_config["goal"],
        backstory=role_config["backstory"],
        llm=build_crewai_llm("narrative_analyzer"),
        verbose=True,
        allow_delegation=False,
    )
