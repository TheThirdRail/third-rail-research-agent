"""Agent configuration and LLM setup using unified LLM provider."""

from typing import Any

from crewai import LLM

from src.core.config import settings
from src.core.llm_provider_docker import (
    LLMProvider,
    get_analysis_router,
    get_llm_router,
)
from src.core.model_normalization import normalize_model_for_provider

_CREWAI_NATIVE_PROVIDERS = {
    LLMProvider.OPENAI.value,
    LLMProvider.ANTHROPIC.value,
    LLMProvider.GEMINI.value,
    "azure",
    "azure_openai",
    "bedrock",
    "aws",
}


def get_llm_config(agent_name: str | None = None) -> dict[str, Any]:
    """Get LLM configuration for CrewAI agents.

    Uses the unified LLMRouter to support multiple providers:
    OpenRouter, Gemini, Anthropic, Groq, OpenAI, LM Studio, Grok,
    Cerebras, SambaNova, Mistral, and Ollama.

    Args:
        agent_name: Optional name of the agent to get specific config for.

    Returns:
        CrewAI-compatible LLM configuration dict.
    """
    router = get_llm_router(agent_name=agent_name)
    return router.get_crewai_config()


def _provider_uses_crewai_litellm(primary_provider: str) -> bool:
    """Return True when CrewAI routes the provider through LiteLLM."""
    return primary_provider.lower() not in _CREWAI_NATIVE_PROVIDERS


def _build_lmstudio_fallbacks(primary_provider: str) -> list[str]:
    """Build LiteLLM fallback list targeting LM Studio for transient failures."""
    if not settings.lmstudio_fallback_enabled:
        return []
    if primary_provider == LLMProvider.LMSTUDIO.value:
        return []
    if not _provider_uses_crewai_litellm(primary_provider):
        return []

    fallback_model = normalize_model_for_provider(
        LLMProvider.LMSTUDIO.value, settings.lmstudio_fallback_model
    )
    if not fallback_model:
        return []
    return [f"lm_studio/{fallback_model}"]


def build_crewai_llm(agent_name: str | None = None) -> LLM:
    """Build a CrewAI LLM object with provider credentials and local fallbacks.

    This ensures CrewAI receives base_url/api_base/api_key and can apply
    LiteLLM-level fallback behavior.
    """
    router = get_llm_router(agent_name=agent_name)
    llm_config = router.get_crewai_config()

    llm_kwargs: dict[str, Any] = {
        "model": llm_config["model"],
        "timeout": 120,
        "max_tokens": 4096,
        "temperature": (
            router.temperature_override
            if router.temperature_override is not None
            else 0.7
        ),
        "max_retries": 2,
    }

    api_key = llm_config.get("api_key")
    if api_key:
        llm_kwargs["api_key"] = api_key

    base_url = llm_config.get("base_url")
    if base_url:
        llm_kwargs["base_url"] = base_url
        llm_kwargs["api_base"] = base_url

    reasoning_effort = llm_config.get("reasoning_effort")
    if reasoning_effort:
        llm_kwargs["reasoning_effort"] = reasoning_effort

    fallbacks = _build_lmstudio_fallbacks(router.provider.value)
    if fallbacks:
        llm_kwargs["fallbacks"] = fallbacks

    return LLM(**llm_kwargs)


def get_analysis_llm_config() -> dict[str, Any]:
    """Get LLM config for analysis tasks (may use different model).

    Returns:
        CrewAI-compatible LLM configuration for analysis tasks.
    """
    router = get_analysis_router()
    return router.get_crewai_config()


# Agent role definitions
AGENT_ROLES = {
    "profile_reader": {
        "role": "Channel Profile Analyst",
        "goal": "Understand the channel's focus areas, worldview, and content preferences",
        "backstory": """You are an expert at understanding content creator profiles.
        You analyze channel descriptions, topic preferences, and worldviews to
        identify what stories would resonate with the creator's audience.""",
    },
    "news_aggregator": {
        "role": "News Scout",
        "goal": "Find relevant news stories from diverse sources across the political spectrum",
        "backstory": """You are a seasoned news aggregator with connections to sources
        across the political spectrum. You know how to find breaking stories,
        trending topics, and underreported news that matters.""",
    },
    "relevance_scorer": {
        "role": "Relevance Analyst",
        "goal": "Rank stories by relevance to the channel's focus areas",
        "backstory": """You specialize in matching news stories to content creator
        profiles. You understand what makes a story relevant, timely, and
        engaging for specific audiences.""",
    },
    "story_parser": {
        "role": "Story Researcher",
        "goal": "Extract and clarify the core details of a news story",
        "backstory": """You are an investigative journalist skilled at cutting through
        noise to find the essential facts. You can take a vague story description
        and turn it into clear, searchable terms.""",
    },
    "semantic_query_expander": {
        "role": "Semantic Query Expander",
        "goal": "Generate alternate search phrases that preserve the current story identity",
        "backstory": """You are a search strategist who rewrites a news story into
        precise alternate phrases. You preserve the same actors, event, and time
        context while accounting for different outlet framing and terminology.""",
    },
    "source_aggregator": {
        "role": "Multi-Source Researcher",
        "goal": "Find all available sources covering a story across the political spectrum",
        "backstory": """You are a research specialist who believes in seeing all sides.
        You systematically search for coverage from left, center, right, and
        independent sources to build a complete picture.""",
    },
    "bias_classifier": {
        "role": "Political Bias Analyst",
        "goal": "Classify news sources on a 9-point political bias scale",
        "backstory": """You are a media analyst with decades of experience studying
        political bias in journalism. You can identify subtle framing, loaded
        language, and partisan slant with high accuracy. You remain objective
        and base classifications on evidence.""",
    },
    "fact_extractor": {
        "role": "Fact-Opinion Separator",
        "goal": "Distinguish verifiable facts from editorial opinions in news coverage",
        "backstory": """You are a fact-checker trained to identify what is verifiable
        versus what is interpretation. You clearly separate objective facts that
        can be confirmed from subjective opinions and analysis.""",
    },
    "rhetorical_analyst": {
        "role": "Rhetorical Manipulation Analyst",
        "goal": "Detect framing tactics, fallacies, loaded rhetoric, and coded political language",
        "backstory": """You are a discourse analyst focused on argument quality and
        media rhetoric. You identify manipulation patterns using evidence-first,
        context-gated reasoning. You avoid overreach and label uncertainty clearly.""",
    },
    "narrative_analyzer": {
        "role": "Narrative Analyst",
        "goal": "Identify mainstream and alternative narratives around a story",
        "backstory": """You study how different outlets frame the same story. You
        can identify the dominant mainstream narrative and contrast it with
        alternative perspectives from independent media.""",
    },
    "visual_evidence": {
        "role": "Visual Evidence Analyst",
        "goal": "Describe only directly observable media evidence without interpretation",
        "backstory": """You inspect images and social-post media carefully. You
        separate visible text, symbols, and objects from inferred intent,
        political meaning, and legal characterization.""",
    },
    "report_writer": {
        "role": "Research Report Writer",
        "goal": "Generate comprehensive, balanced research reports with video outlines",
        "backstory": """You are a skilled report writer who creates clear, organized
        research documents. You present facts first, clearly label opinions, and
        provide actionable video outlines for content creators.""",
    },
}
