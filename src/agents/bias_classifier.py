"""Bias Classifier Agent for political bias analysis."""

from crewai import Agent

from src.agents.config import AGENT_ROLES, get_llm_config
from src.tools.bias_classifier import BiasClassifierTool


def create_bias_classifier_agent() -> Agent:
    """Create the bias classifier agent.

    This agent classifies news sources on a 9-point
    political bias scale from -4 (Far Left) to +4 (Far Right).
    Uses LLM-based classification for unknown sources.
    """
    config = AGENT_ROLES["bias_classifier"]
    llm_config = get_llm_config(agent_name="bias_classifier")

    return Agent(
        role=config["role"],
        goal=config["goal"],
        backstory=config["backstory"],
        tools=[BiasClassifierTool()],
        llm=llm_config.get("model"),
        verbose=True,
        allow_delegation=False,
    )
