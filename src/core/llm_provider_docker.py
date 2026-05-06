"""Unified LLM Provider using LiteLLM.

Supports multiple providers through a single interface:
- OpenRouter (free tier available)
- Google Gemini (free tier available)
- Anthropic Claude
- Groq (free tier available)
- OpenAI / Compatible
- LM Studio (local OpenAI-compatible)
- Grok (xAI)
- Cerebras (free tier available)
- SambaNova
- Mistral AI (free tier available)
- Ollama (local)
"""

import asyncio
import logging
import os
import re
import threading
import time
from enum import Enum
from typing import Any

from litellm import acompletion, completion, completion_cost
from pydantic import BaseModel

from src.core.budget_service import get_budget_service
from src.core.exceptions import BudgetExceededError, RateLimitExceededError
from src.core.lmstudio_utils import (
    normalize_lmstudio_base_url,
    resolve_lmstudio_api_key,
)
from src.core.model_normalization import (
    normalize_model_for_provider,
    normalize_provider_name,
)

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    OPENROUTER = "openrouter"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"
    GROQ = "groq"
    OPENAI = "openai"
    LMSTUDIO = "lmstudio"
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
    LLMProvider.OPENROUTER: "openrouter/free",
    LLMProvider.GEMINI: "gemini-2.5-flash",
    LLMProvider.ANTHROPIC: "claude-3-5-sonnet-20241022",
    LLMProvider.GROQ: "llama-3.3-70b-versatile",
    LLMProvider.OPENAI: "gpt-4o-mini",
    LLMProvider.LMSTUDIO: "qwen2.5-7b-instruct",
    LLMProvider.GROK: "grok-2-latest",
    LLMProvider.CEREBRAS: "llama-3.3-70b",
    LLMProvider.SAMBANOVA: "Meta-Llama-3.3-70B-Instruct",
    LLMProvider.MISTRAL: "mistral-small-latest",
    LLMProvider.OLLAMA: "llama3.1:8b",
}


class LLMRouter:
    """Routes LLM requests to the configured provider using LiteLLM."""

    _RATE_LIMIT_RETRIES = 5
    _RATE_LIMIT_BASE_DELAY = 5.0
    _RATE_LIMIT_MAX_DELAY = 120.0
    _RETRY_AFTER_REGEX = re.compile(r"retry in ([0-9]+(?:\\.[0-9]+)?)s", re.IGNORECASE)
    _PROVIDER_CONCURRENCY = 1
    _provider_semaphores: dict["LLMProvider", threading.BoundedSemaphore] = {}
    _provider_async_semaphores: dict["LLMProvider", asyncio.Semaphore] = {}
    _provider_lock = threading.Lock()

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
                        self._agent_reasoning_effort = agent_config.reasoning_effort
            except Exception:
                logger.warning(
                    f"Failed to load config for agent {agent_name}", exc_info=True
                )
                agent_config = None
        if agent_name and not agent_config:
            logger.info(
                "No persisted configuration found for agent=%s; using provider/model defaults.",
                agent_name,
            )

        # Get provider: arg > agent_config > global config > env > default
        provider_str = provider
        if not provider_str and agent_config and agent_config.provider:
            provider_str = agent_config.provider

        provider_str = (
            provider_str
            or settings.llm_provider
            or os.getenv("LLM_PROVIDER", "openrouter")
        )
        normalized_provider = normalize_provider_name(provider_str) or "openrouter"
        self.provider = LLMProvider(normalized_provider)

        # Get model: arg > agent_config > global config > env > fallback
        model_str = model
        if not model_str and agent_config and agent_config.model:
            model_str = agent_config.model

        raw_model = (
            model_str
            or settings.selected_model
            or os.getenv("SELECTED_MODEL")
            or FALLBACK_MODELS.get(self.provider, "")
        )
        self.model = normalize_model_for_provider(self.provider.value, raw_model)
        if raw_model != self.model:
            logger.info(
                "Normalized model for provider=%s: raw=%s normalized=%s",
                self.provider.value,
                raw_model,
                self.model,
            )

        # Temperature (if set in agent config, currently used in completion methods)
        self.temperature_override = agent_config.temperature if agent_config else None
        self.free_tier = bool(agent_config.free_tier) if agent_config else False
        self.reasoning_effort = agent_config.reasoning_effort if agent_config else None

        # Get API key and base URL for provider
        self.api_key = self._get_api_key()
        self.base_url = self._get_base_url()
        if self._codex_bridge_testing_enabled(settings):
            self._validate_codex_oauth_bridge_config(settings)

        # Build LiteLLM model string
        self.litellm_model = self._build_model_string()

        logger.info(
            "LLMRouter initialized: agent=%s, provider=%s, model=%s, base_url=%s",
            agent_name,
            self.provider.value,
            self.model,
            self.base_url,
        )

    def _codex_bridge_testing_enabled(self, settings: Any) -> bool:
        """Return True when this router should apply Codex bridge guards."""
        return (
            bool(getattr(settings, "codex_oauth_testing_enabled", False))
            and getattr(settings, "codex_oauth_mode", "disabled")
            == "openai_compatible_bridge"
            and self.provider == LLMProvider.OPENAI
        )

    def _validate_codex_oauth_bridge_config(self, settings: Any) -> None:
        """Validate local Codex bridge settings before OpenAI-compatible calls."""
        from src.core.codex_oauth.bridge import validate_bridge_mode

        validate_bridge_mode(
            settings,
            provider=self.provider.value,
            require_settings_provider=False,
        )

    def _validate_codex_oauth_messages(self, messages: list[dict[str, str]]) -> None:
        """Apply prompt-size guard for Codex bridge testing only."""
        from src.core.config import settings

        if not self._codex_bridge_testing_enabled(settings):
            return

        from src.core.codex_oauth.safety import validate_prompt_length

        prompt = "\n".join(str(message.get("content", "")) for message in messages)
        validate_prompt_length(prompt, settings.codex_max_prompt_chars)

    def _model_is_budget_free(self) -> bool:
        """Return True when budget free-only mode should allow this router."""
        from src.core.config import settings

        return (
            ":free" in self.model.lower()
            or self.provider in {LLMProvider.OLLAMA, LLMProvider.LMSTUDIO}
            or self._codex_bridge_testing_enabled(settings)
        )

    def _is_rate_limit_error(self, exc: Exception) -> bool:
        """Best-effort detection of 429 / RESOURCE_EXHAUSTED errors."""
        status_code = getattr(exc, "status_code", None)
        if status_code in {429, 503}:
            return True
        message = str(exc).lower()
        if "resource_exhausted" in message:
            return True
        if (
            "rate_limited" in message
            or "rate limit" in message
            or "rate_limit" in message
        ):
            return True
        if "over capacity" in message or "service unavailable" in message:
            return True
        if "internal_server_error" in message:
            return True
        return "429" in message

    def _quota_zero(self, exc: Exception) -> bool:
        """Detect if quota limit is zero (skip retries)."""
        return re.search(r"limit:\s*0", str(exc), re.IGNORECASE) is not None

    def _extract_retry_after(self, exc: Exception) -> float | None:
        """Extract retry-after seconds from exception message if present."""
        message = str(exc)
        match = self._RETRY_AFTER_REGEX.search(message)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None

    def _compute_backoff(self, attempt: int, exc: Exception) -> float:
        """Compute backoff delay honoring retry-after if present."""
        base_delay = self._RATE_LIMIT_BASE_DELAY * (2**attempt)
        retry_after = self._extract_retry_after(exc) or 0.0
        delay = max(base_delay, retry_after)
        return min(delay, self._RATE_LIMIT_MAX_DELAY)

    def _get_provider_semaphore(self) -> threading.BoundedSemaphore:
        """Get or create a per-provider semaphore for sync calls."""
        with self._provider_lock:
            semaphore = self._provider_semaphores.get(self.provider)
            if semaphore is None:
                semaphore = threading.BoundedSemaphore(self._PROVIDER_CONCURRENCY)
                self._provider_semaphores[self.provider] = semaphore
        return semaphore

    def _get_provider_async_semaphore(self) -> asyncio.Semaphore:
        """Get or create a per-provider semaphore for async calls."""
        with self._provider_lock:
            semaphore = self._provider_async_semaphores.get(self.provider)
            if semaphore is None:
                semaphore = asyncio.Semaphore(self._PROVIDER_CONCURRENCY)
                self._provider_async_semaphores[self.provider] = semaphore
        return semaphore

    def _is_openrouter_not_found(self, exc: Exception) -> bool:
        """Detect OpenRouter model-not-found failures suitable for one-time recovery."""
        if self.provider != LLMProvider.OPENROUTER:
            return False
        message = str(exc).lower()
        return (
            "notfounderror" in message
            or "openrouterexception" in message
            or "no endpoints found" in message
        )

    @staticmethod
    def _is_text_model_id(model_id: str) -> bool:
        """Best-effort filter for text-capable model IDs."""
        lower = model_id.lower()
        non_text_tokens = (
            "vision",
            "-vl",
            "_vl",
            "image",
            "audio",
            "video",
            "speech",
        )
        return not any(token in lower for token in non_text_tokens)

    def _rank_openrouter_recovery_models(self, models: list[Any]) -> list[str]:
        """Rank replacement model IDs deterministically for recovery."""
        ids = sorted({getattr(m, "id", "") for m in models if getattr(m, "id", "")})
        free_ids = sorted(
            {
                getattr(m, "id", "")
                for m in models
                if getattr(m, "id", "") and bool(getattr(m, "is_free", False))
            }
        )
        free_text_ids = [mid for mid in free_ids if self._is_text_model_id(mid)]

        ordered: list[str] = []
        if "openrouter/free" in ids:
            ordered.append("openrouter/free")
        ordered.extend(free_text_ids)
        ordered.extend(free_ids)
        ordered.extend(ids)

        deduped: list[str] = []
        seen: set[str] = set()
        for model_id in ordered:
            if model_id in seen:
                continue
            seen.add(model_id)
            deduped.append(model_id)
        return deduped

    def _set_runtime_model(self, model_id: str) -> bool:
        """Update normalized model and litellm model string for retries."""
        normalized = normalize_model_for_provider(self.provider.value, model_id)
        if not normalized:
            return False
        self.model = normalized
        self.litellm_model = self._build_model_string()
        return True

    def _list_openrouter_models_sync(self) -> list[Any]:
        """Fetch OpenRouter models from registry in sync contexts."""
        from src.core.model_registry import get_model_registry

        registry = get_model_registry()
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(registry.list_models("openrouter", force_refresh=True))

        models_box: list[list[Any]] = []
        errors: list[Exception] = []

        def _worker() -> None:
            try:
                models_box.append(
                    asyncio.run(registry.list_models("openrouter", force_refresh=True))
                )
            except Exception as worker_exc:
                errors.append(worker_exc)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        thread.join()

        if errors:
            raise errors[0]
        return models_box[0] if models_box else []

    def _recover_openrouter_model_sync(self, exc: Exception) -> bool:
        """Try a one-time OpenRouter model recovery in sync path."""
        if not self._is_openrouter_not_found(exc):
            return False

        try:
            models = self._list_openrouter_models_sync()
        except Exception:
            logger.warning("OpenRouter recovery failed to list models", exc_info=True)
            return False

        current = normalize_model_for_provider(self.provider.value, self.model)
        for candidate in self._rank_openrouter_recovery_models(models):
            if normalize_model_for_provider(self.provider.value, candidate) == current:
                continue
            old_model = self.model
            if not self._set_runtime_model(candidate):
                continue
            logger.warning(
                "OpenRouter model recovery applied (sync): old_model=%s new_model=%s cause=%s",
                old_model,
                self.model,
                str(exc)[:240],
            )
            return True
        return False

    async def _recover_openrouter_model_async(self, exc: Exception) -> bool:
        """Try a one-time OpenRouter model recovery in async path."""
        if not self._is_openrouter_not_found(exc):
            return False

        from src.core.model_registry import get_model_registry

        try:
            models = await get_model_registry().list_models(
                "openrouter", force_refresh=True
            )
        except Exception:
            logger.warning("OpenRouter recovery failed to list models", exc_info=True)
            return False

        current = normalize_model_for_provider(self.provider.value, self.model)
        for candidate in self._rank_openrouter_recovery_models(models):
            if normalize_model_for_provider(self.provider.value, candidate) == current:
                continue
            old_model = self.model
            if not self._set_runtime_model(candidate):
                continue
            logger.warning(
                "OpenRouter model recovery applied (async): old_model=%s new_model=%s cause=%s",
                old_model,
                self.model,
                str(exc)[:240],
            )
            return True
        return False

    def _call_with_backoff(self, call_fn, sleep_fn):
        if not self.free_tier:
            return call_fn()
        for attempt in range(self._RATE_LIMIT_RETRIES + 1):
            try:
                return call_fn()
            except Exception as exc:
                if not self._is_rate_limit_error(exc):
                    raise
                if self._quota_zero(exc):
                    raise RateLimitExceededError(
                        f"{self.provider.value} quota is 0 for this project; enable billing or switch provider."
                    ) from exc
                if attempt >= self._RATE_LIMIT_RETRIES:
                    raise RateLimitExceededError(
                        f"{self.provider.value} rate limit exceeded; please retry later."
                    ) from exc
                delay = self._compute_backoff(attempt, exc)
                sleep_fn(delay)
        raise RateLimitExceededError(
            f"{self.provider.value} rate limit exceeded; please retry later."
        )

    async def _call_with_backoff_async(self, call_fn, sleep_fn):
        if not self.free_tier:
            return await call_fn()
        for attempt in range(self._RATE_LIMIT_RETRIES + 1):
            try:
                return await call_fn()
            except Exception as exc:
                if not self._is_rate_limit_error(exc):
                    raise
                if self._quota_zero(exc):
                    raise RateLimitExceededError(
                        f"{self.provider.value} quota is 0 for this project; enable billing or switch provider."
                    ) from exc
                if attempt >= self._RATE_LIMIT_RETRIES:
                    raise RateLimitExceededError(
                        f"{self.provider.value} rate limit exceeded; please retry later."
                    ) from exc
                delay = self._compute_backoff(attempt, exc)
                await sleep_fn(delay)
        raise RateLimitExceededError(
            f"{self.provider.value} rate limit exceeded; please retry later."
        )

    def _get_api_key(self) -> str | None:
        """Get API key for the current provider."""
        from src.core.config import settings

        key_mapping = {
            LLMProvider.OPENROUTER: "OPENROUTER_API_KEY",
            LLMProvider.GEMINI: "GOOGLE_API_KEY",
            LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
            LLMProvider.GROQ: "GROQ_API_KEY",
            LLMProvider.OPENAI: "OPENAI_API_KEY",
            LLMProvider.LMSTUDIO: "LM_STUDIO_API_KEY",
            LLMProvider.GROK: "XAI_API_KEY",
            LLMProvider.CEREBRAS: "CEREBRAS_API_KEY",
            LLMProvider.SAMBANOVA: "SAMBANOVA_API_KEY",
            LLMProvider.MISTRAL: "MISTRAL_API_KEY",
            LLMProvider.OLLAMA: None,  # No API key needed
        }
        env_var = key_mapping.get(self.provider)
        if self.provider == LLMProvider.GEMINI:
            return os.getenv(env_var) or os.getenv("GEMINI_API_KEY")
        if self.provider == LLMProvider.LMSTUDIO:
            return resolve_lmstudio_api_key(
                os.getenv("LM_STUDIO_API_KEY"),
                os.getenv("LMSTUDIO_API_KEY"),
                settings.lmstudio_api_key,
            )
        return os.getenv(env_var) if env_var else None

    def _get_base_url(self) -> str | None:
        """Get base URL for the current provider."""
        from src.core.config import settings

        url_mapping = {
            LLMProvider.OPENROUTER: os.getenv(
                "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
            ),
            LLMProvider.OLLAMA: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            LLMProvider.OPENAI: os.getenv("OPENAI_BASE_URL")
            or settings.openai_base_url,
            LLMProvider.LMSTUDIO: normalize_lmstudio_base_url(
                os.getenv("LM_STUDIO_API_BASE")
                or os.getenv("LM_STUDIO_BASE_URL")
                or os.getenv("LMSTUDIO_BASE_URL")
                or settings.lmstudio_base_url
            ),
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
        - lm_studio/model-name
        - ollama/model-name
        """
        prefix_mapping = {
            LLMProvider.OPENROUTER: "openrouter",
            LLMProvider.GEMINI: "gemini",
            LLMProvider.ANTHROPIC: "anthropic",
            LLMProvider.GROQ: "groq",
            LLMProvider.OPENAI: "openai",
            LLMProvider.LMSTUDIO: "lm_studio",
            LLMProvider.GROK: "xai",
            LLMProvider.CEREBRAS: "cerebras",
            LLMProvider.SAMBANOVA: "sambanova",
            LLMProvider.MISTRAL: "mistral",
            LLMProvider.OLLAMA: "ollama",
        }
        prefix = prefix_mapping.get(self.provider, "openai")
        normalized_model = normalize_model_for_provider(self.provider.value, self.model)
        return f"{prefix}/{normalized_model}"

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
        self._validate_codex_oauth_messages(messages)

        # Budget pre-flight check
        budget = get_budget_service()
        model_is_free = self._model_is_budget_free()

        if not budget.can_afford(model_is_free):
            status = budget.get_status()
            raise BudgetExceededError(
                f"Budget exceeded. Current: ${status['current_spend']:.4f}, "
                f"Limit: ${status['limit']:.2f}"
            )

        def _call_completion():
            completion_kwargs = dict(kwargs)
            reasoning_effort = self._chat_completion_reasoning_effort()
            if reasoning_effort:
                completion_kwargs["reasoning_effort"] = reasoning_effort
            return completion(
                model=self.litellm_model,
                messages=messages,
                api_key=self.api_key,
                base_url=self.base_url,
                temperature=self._chat_completion_temperature(temperature),
                max_tokens=max_tokens or 4096,
                **completion_kwargs,
            )

        def _run_once():
            if self.free_tier:
                semaphore = self._get_provider_semaphore()
                semaphore.acquire()
                try:
                    return self._call_with_backoff(_call_completion, time.sleep)
                finally:
                    semaphore.release()
            return _call_completion()

        try:
            response = _run_once()
        except Exception as exc:
            if self._recover_openrouter_model_sync(exc):
                response = _run_once()
            else:
                raise

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
        self._validate_codex_oauth_messages(messages)

        # Budget pre-flight check
        budget = get_budget_service()
        model_is_free = self._model_is_budget_free()

        if not budget.can_afford(model_is_free):
            status = budget.get_status()
            raise BudgetExceededError(
                f"Budget exceeded. Current: ${status['current_spend']:.4f}, "
                f"Limit: ${status['limit']:.2f}"
            )

        async def _call_acompletion():
            completion_kwargs = dict(kwargs)
            reasoning_effort = self._chat_completion_reasoning_effort()
            if reasoning_effort:
                completion_kwargs["reasoning_effort"] = reasoning_effort
            return await acompletion(
                model=self.litellm_model,
                messages=messages,
                api_key=self.api_key,
                base_url=self.base_url,
                temperature=self._chat_completion_temperature(temperature),
                max_tokens=max_tokens or 4096,
                **completion_kwargs,
            )

        async def _run_once():
            if self.free_tier:
                semaphore = self._get_provider_async_semaphore()
                async with semaphore:
                    return await self._call_with_backoff_async(
                        _call_acompletion, asyncio.sleep
                    )
            return await _call_acompletion()

        try:
            response = await _run_once()
        except Exception as exc:
            if await self._recover_openrouter_model_async(exc):
                response = await _run_once()
            else:
                raise

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
        config: dict[str, Any] = {
            "model": self.litellm_model,
            "provider": self.provider.value,
            "raw_model": self.model,
            "free_tier": self.free_tier,
        }

        if self.api_key:
            config["api_key"] = self.api_key
        if self.base_url:
            config["base_url"] = self.base_url
            config["api_base"] = self.base_url
        reasoning_effort = getattr(self, "reasoning_effort", None)
        if reasoning_effort:
            config["reasoning_effort"] = reasoning_effort

        return config

    def _chat_completion_reasoning_effort(self) -> str | None:
        """Return a LiteLLM chat-completions-safe reasoning effort value."""
        if self.provider != LLMProvider.OPENAI:
            return None
        reasoning_effort = getattr(self, "reasoning_effort", None)
        if reasoning_effort in {"low", "medium", "high"}:
            return reasoning_effort
        return None

    def _chat_completion_temperature(self, temperature: float | None) -> float:
        """Return a LiteLLM-safe chat completion temperature."""
        if self.provider == LLMProvider.OPENAI and self.model.lower().startswith(
            "gpt-5"
        ):
            return 1.0
        if self.temperature_override is not None:
            return self.temperature_override
        if temperature is not None:
            return temperature
        return 0.7


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
