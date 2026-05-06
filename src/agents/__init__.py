"""CrewAI agent definitions."""

from src.agents.bias_classifier import create_bias_classifier_agent
from src.agents.config import (
    AGENT_ROLES,
    build_crewai_llm,
    get_analysis_llm_config,
    get_llm_config,
)
from src.agents.fact_extractor import create_fact_extractor_agent
from src.agents.narrative_analyzer import create_narrative_analyzer_agent
from src.agents.news_aggregator import create_news_aggregator_agent
from src.agents.profile_reader import create_profile_reader_agent, get_channel_context
from src.agents.relevance_scorer import create_relevance_scorer_agent
from src.agents.report_writer import create_report_writer_agent
from src.agents.rhetorical_analyst import create_rhetorical_analyst_agent
from src.agents.source_aggregator import create_source_aggregator_agent

__all__ = [
    # Agent factories
    "create_news_aggregator_agent",
    "create_source_aggregator_agent",
    "create_bias_classifier_agent",
    "create_fact_extractor_agent",
    "create_rhetorical_analyst_agent",
    "create_narrative_analyzer_agent",
    "create_report_writer_agent",
    "create_profile_reader_agent",
    "create_relevance_scorer_agent",
    # Utilities
    "get_channel_context",
    # Config
    "AGENT_ROLES",
    "build_crewai_llm",
    "get_llm_config",
    "get_analysis_llm_config",
]
