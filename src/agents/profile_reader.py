"""Profile Reader Agent for understanding channel scope."""

from crewai import Agent

from src.agents.config import AGENT_ROLES, get_llm_config
from src.core.config import settings
from src.tools.channel_profile_loader import load_channel_profile


def create_profile_reader_agent() -> Agent:
    """Create the profile reader agent.

    This agent reads and understands the channel's profile,
    including topics, worldview, and content preferences.
    """
    config = AGENT_ROLES["profile_reader"]
    llm_config = get_llm_config(agent_name="profile_reader")

    return Agent(
        role=config["role"],
        goal=config["goal"],
        backstory=config["backstory"],
        tools=[],  # Profile loaded directly, no tools needed
        llm=llm_config.get("model"),
        verbose=True,
        allow_delegation=False,
    )


def get_channel_context() -> str:
    """Get channel profile context for agent prompts.

    Returns:
        Formatted string with channel context for task prompts
    """
    try:
        scope = load_channel_profile(settings.channel_profile_path)
        return f"""Channel Profile:
- Name: {scope.name}
- Worldview: {scope.worldview}
- Description: {scope.description[:500]}
- Topics: {", ".join(scope.topics[:10])}
"""
    except Exception:
        return "Channel Profile: Not configured. Using default settings."
