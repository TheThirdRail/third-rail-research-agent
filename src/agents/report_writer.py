"""Report Writer Agent for generating comprehensive reports."""

from crewai import Agent

from src.agents.config import AGENT_ROLES, get_llm_config


def create_report_writer_agent() -> Agent:
    """Create the report writer agent.

    This agent generates comprehensive research reports
    with facts, analysis, and video outlines.
    """
    config = AGENT_ROLES["report_writer"]

    return Agent(
        role=config["role"],
        goal=config["goal"],
        backstory=config["backstory"],
        tools=[],  # Uses LLM for writing, no external tools
        verbose=True,
        allow_delegation=False,
    )
