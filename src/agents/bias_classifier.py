"""Bias Classifier Agent for political bias analysis."""

from crewai import Agent

from src.agents.config import AGENT_ROLES, get_llm_config
from src.tools import BiasClassifierTool, MultiBiasClassifierTool


def create_bias_classifier_agent() -> Agent:
    """Create the bias classifier agent.

    This agent classifies news sources on a 9-point
    political bias scale from -4 (Far Left) to +4 (Far Right).
    """
    config = AGENT_ROLES["bias_classifier"]

    return Agent(
        role=config["role"],
        goal=config["goal"],
        backstory=config["backstory"],
        tools=[BiasClassifierTool(), MultiBiasClassifierTool()],
        verbose=True,
        allow_delegation=False,
    )
