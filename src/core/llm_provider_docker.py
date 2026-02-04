"""Unified LLM Provider using LiteLLM.

Supports multiple providers through a single interface:
- OpenRouter (free tier available)
- Google Gemini (free tier available)
- Anthropic Claude
- Groq (free tier available)
- OpenAI / Compatible
- Grok (xAI)
- Cerebras (free tier available)
- SambaNova
- Mistral AI (free tier available)
- Ollama (local)
"""

import logging
import os
from enum import Enum
from typing import Any

from litellm import acompletion, completion, completion_cost
from pydantic import BaseModel

from src.core.budget_service import get_budget_service
from src.core.exceptions import BudgetExceededError

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    OPENROUTER = "openrouter"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"
    GROQ = "groq"
    OPENAI = "openai"
    GROK = "grok"
    CEREBRAS = "cerebras"
    SAMBANOVA = "sambanova"
    MISTRAL = "mistral"
    OLLAMA = "ollama"


class LLMConfig(BaseModel):
    """Configuration for an LLM provider."""

    provider: LLMProvider
    model: str
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.7
    max_tokens: int = 4096


# Fallback models per provider (used only if no model is selected)
FALLBACK_MODELS: dict[LLMProvider, str] = {
    LLMProvider.OPENROUTER: "meta-llama/llama-3.2-11b-vision-instruct:free",
    LLMProvider.GEMINI: "gemini-2.5-flash",
    LLMProvider.ANTHROPIC: "claude-3-5-sonnet-20241022",
    LLMProvider.GROQ: "llama-3.3-70b-versatile",
    LLMProvider.OPENAI: "gpt-4o-mini",
    LLMProvider.GROK: "grok-2-latest",
    LLMProvider.CEREBRAS: "llama-3.3-70b",
    LLMProvider.SAMBANOVA: "Meta-Llama-3.3-70B-Instruct",
    LLMProvider.MISTRAL: "mistral-small-latest",
    LLMProvider.OLLAMA: "llama3.1:8b",
}


class LLMRouter:
    """Routes LLM requests to the configured provider using LiteLLM."""

    def __init__(
        self,
        provider: LLMProvider | str | None = None,
        model: str | None = None,
        agent_name: str | None = None,
    ):
        """Initialize LLM router.

        Args:
            provider: LLM provider to use. Defaults to env var LLM_PROVIDER.
            model: Model to use. Defaults to selected_model from config or fallback.
        """
        from src.core.config import settings
        from src.database.session import get_session
        from src.services.agent_config_service import AgentConfigService

        # Try to load agent-specific config
        agent_config = None
        if agent_name:
            try:
                # Use a fresh session for config lookup since this might be called async/sync
                with get_session() as session:
                    service = AgentConfigService(session)
                    agent_config = service.get_config(agent_name)
                    # We need to detach or copy the values since session closes
                    if agent_config:
                        # Extract values we need
                        self._agent_provider = agent_config.provider
                        self._agent_model = agent_config.model
                        self._agent_temp = agent_config.temperature
            except Exception:
                logger.warning(
                    f"Failed to load config for agent {agent_name}", exc_info=True
                )
                agent_config = None

        # Get provider: arg > agent_config > global config > env > default
        provider_str = provider
        if not provider_str and agent_config and agent_config.provider:
            provider_str = agent_config.provider

        provider_str = (
            provider_str
            or settings.llm_provider
            or os.getenv("LLM_PROVIDER", "openrouter")
        )
        self.provider = LLMProvider(provider_str.lower())

        # Get model: arg > agent_config > global config > env > fallback
        model_str = model
        if not model_str and agent_config and agent_config.model:
            model_str = agent_config.model

        self.model = (
            model_str
            or settings.selected_model
            or os.getenv("SELECTED_MODEL")
            or FALLBACK_MODELS.get(self.provider, "")
        )

        # Temperature (if set in agent config, currently used in completion methods)
        self.temperature_override = agent_config.temperature if agent_config else None

        # Get API key and base URL for provider
        self.api_key = self._get_api_key()
        self.base_url = self._get_base_url()

        # Build LiteLLM model string
        self.litellm_model = self._build_model_string()

        logger.info(
            f"LLMRouter initialized: agent={agent_name}, provider={self.provider.value}, model={self.model}"
        )

    def _get_api_key(self) -> str | None:
        """Get API key for the current provider."""
        key_mapping = {
            LLMProvider.OPENROUTER: "OPENROUTER_API_KEY",
            LLMProvider.GEMINI: "GOOGLE_API_KEY",
            LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
            LLMProvider.GROQ: "GROQ_API_KEY",
            LLMProvider.OPENAI: "OPENAI_API_KEY",
            LLMProvider.GROK: "XAI_API_KEY",
            LLMProvider.CEREBRAS: "CEREBRAS_API_KEY",
            LLMProvider.SAMBANOVA: "SAMBANOVA_API_KEY",
            LLMProvider.MISTRAL: "MISTRAL_API_KEY",
            LLMProvider.OLLAMA: None,  # No API key needed
        }
        env_var = key_mapping.get(self.provider)
        if self.provider == LLMProvider.GEMINI:
            return os.getenv(env_var) or os.getenv("GEMINI_API_KEY")
        return os.getenv(env_var) if env_var else None

    def _get_base_url(self) -> str | None:
        """Get base URL for the current provider."""
        url_mapping = {
            LLMProvider.OPENROUTER: os.getenv(
                "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
            ),
            LLMProvider.OLLAMA: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            LLMProvider.OPENAI: os.getenv(
                "OPENAI_BASE_URL"
            ),  # Optional for compatible APIs
            LLMProvider.GROK: "https://api.x.ai/v1",
            LLMProvider.CEREBRAS: "https://api.cerebras.ai/v1",
            LLMProvider.SAMBANOVA: "https://api.sambanova.ai/v1",
            LLMProvider.MISTRAL: "https://api.mistral.ai/v1",
        }
        return url_mapping.get(self.provider)

    def _build_model_string(self) -> str:
        """Build LiteLLM-compatible model string.

        LiteLLM uses prefixes to route to correct provider:
        - openrouter/model-name
        - gemini/model-name
        - anthropic/model-name
        - groq/model-name
        - openai/model-name
        - ollama/model-name
        """
        prefix_mapping = {
            LLMProvider.OPENROUTER: "openrouter",
            LLMProvider.GEMINI: "gemini",
            LLMProvider.ANTHROPIC: "anthropic",
            LLMProvider.GROQ: "groq",
            LLMProvider.OPENAI: "openai",
            LLMProvider.GROK: "xai",
            LLMProvider.CEREBRAS: "cerebras",
            LLMProvider.SAMBANOVA: "sambanova",
            LLMProvider.MISTRAL: "mistral",
            LLMProvider.OLLAMA: "ollama",
        }
        prefix = prefix_mapping.get(self.provider, "openai")
        return f"{prefix}/{self.model}"

    def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Synchronous completion with budget enforcement.

        Args:
            messages: Chat messages in OpenAI format
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional LiteLLM parameters

        Returns:
            Generated text content

        Raises:
            BudgetExceededError: If budget limit is exceeded.
        """
        # Budget pre-flight check
        budget = get_budget_service()
        model_is_free = (
            ":free" in self.model.lower() or self.provider == LLMProvider.OLLAMA
        )

        if not budget.can_afford(model_is_free):
            status = budget.get_status()
            raise BudgetExceededError(
                f"Budget exceeded. Current: ${status['current_spend']:.4f}, "
                f"Limit: ${status['limit']:.2f}"
            )

        response = completion(
            model=self.litellm_model,
            messages=messages,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=self.temperature_override or temperature or 0.7,
            max_tokens=max_tokens or 4096,
            **kwargs,
        )

        # Track cost (non-fatal if fails)
        try:
            cost = completion_cost(completion_response=response)
            budget.track_spend(cost)
        except Exception:
            pass  # Cost tracking failure is non-fatal

        return response.choices[0].message.content

    async def acomplete(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Asynchronous completion with budget enforcement.

        Args:
            messages: Chat messages in OpenAI format
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional LiteLLM parameters

        Returns:
            Generated text content

        Raises:
            BudgetExceededError: If budget limit is exceeded.
        """
        # Budget pre-flight check
        budget = get_budget_service()
        model_is_free = (
            ":free" in self.model.lower() or self.provider == LLMProvider.OLLAMA
        )

        if not budget.can_afford(model_is_free):
            status = budget.get_status()
            raise BudgetExceededError(
                f"Budget exceeded. Current: ${status['current_spend']:.4f}, "
                f"Limit: ${status['limit']:.2f}"
            )

        response = await acompletion(
            model=self.litellm_model,
            messages=messages,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=temperature or 0.7,
            max_tokens=max_tokens or 4096,
            **kwargs,
        )

        # Track cost (non-fatal if fails)
        try:
            cost = completion_cost(completion_response=response)
            budget.track_spend(cost)
        except Exception:
            pass  # Cost tracking failure is non-fatal

        return response.choices[0].message.content

    def get_crewai_config(self) -> dict[str, Any]:
        """Get configuration dict for CrewAI agents.

        Returns:
            Dict with model, api_key, and base_url for CrewAI LLM config
        """
        config: dict[str, Any] = {"model": self.litellm_model}

        if self.api_key:
            config["api_key"] = self.api_key
        if self.base_url:
            config["base_url"] = self.base_url

        return config


def get_llm_router(
    provider: LLMProvider | str | None = None,
    model: str | None = None,
    agent_name: str | None = None,
) -> LLMRouter:
    """Factory function to create an LLM router.

    Args:
        provider: Optional provider override
        model: Optional model override

    Returns:
        Configured LLMRouter instance
    """
    return LLMRouter(provider=provider, model=model, agent_name=agent_name)


def get_analysis_router() -> LLMRouter:
    """Get router configured for analysis tasks (may use different model).

    Returns:
        LLMRouter configured with ANALYSIS_MODEL
    """
    analysis_model = os.getenv("ANALYSIS_MODEL")
    return LLMRouter(model=analysis_model)
