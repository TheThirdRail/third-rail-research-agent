"""Model Registry - Dynamic model fetching from LLM providers."""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from src.core.config import settings
from src.core.lmstudio_utils import (
    lmstudio_model_endpoints,
    resolve_lmstudio_api_key,
)
from src.core.model_normalization import (
    normalize_model_for_provider,
    normalize_provider_name,
)

logger = logging.getLogger(__name__)

# Cache TTL in seconds (1 hour)
CACHE_TTL = 3600


@dataclass
class ModelInfo:
    """Information about an available model."""

    id: str
    name: str
    provider: str
    is_free: bool = False
    input_cost_per_m: float = 0.0
    output_cost_per_m: float = 0.0
    context_length: int = 0
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        display_name = self.name
        if self.provider == "openrouter" and self.is_free:
            display_name = f"{self.name} (Free)"
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "is_free": self.is_free,
            "input_cost_per_m": self.input_cost_per_m,
            "output_cost_per_m": self.output_cost_per_m,
            "context_length": self.context_length,
            "description": self.description,
            "display_name": display_name,
        }


@dataclass
class CachedModels:
    """Cached model list with timestamp."""

    models: list[ModelInfo] = field(default_factory=list)
    timestamp: float = 0.0

    def is_valid(self) -> bool:
        """Check if cache is still valid."""
        return time.time() - self.timestamp < CACHE_TTL


class ModelRegistry:
    """Registry for fetching and caching available models from providers."""

    def __init__(self) -> None:
        self._cache: dict[str, CachedModels] = {}
        self._client: httpx.AsyncClient | None = None

    @staticmethod
    def _normalize_provider(provider: str) -> str:
        """Normalize provider aliases to canonical names."""
        return normalize_provider_name(provider) or "openrouter"

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def list_models(
        self, provider: str | None = None, force_refresh: bool = False
    ) -> list[ModelInfo]:
        """List all available models, optionally filtered by provider.

        Args:
            provider: Filter to specific provider, or None for all
            force_refresh: Skip cache and refetch from provider APIs

        Returns:
            List of available models
        """
        if provider:
            return await self._fetch_provider_models(
                self._normalize_provider(provider),
                force_refresh=force_refresh,
            )

        # Fetch from all configured providers
        all_models: list[ModelInfo] = []
        providers = self._get_configured_providers()

        tasks = [
            self._fetch_provider_models(p, force_refresh=force_refresh)
            for p in providers
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_models.extend(result)
            elif isinstance(result, Exception):
                logger.warning(f"Failed to fetch models: {result}")

        return all_models

    def _get_configured_providers(self) -> list[str]:
        """Get list of providers with API keys configured."""
        providers = []

        if settings.openrouter_api_key:
            providers.append("openrouter")
        if settings.google_api_key:
            providers.append("gemini")
        if settings.anthropic_api_key:
            providers.append("anthropic")
        if settings.groq_api_key:
            providers.append("groq")
        if settings.openai_api_key:
            providers.append("openai")
        if self._lmstudio_base_url() and (
            settings.lmstudio_fallback_enabled
            or self._normalize_provider(settings.llm_provider) == "lmstudio"
        ):
            providers.append("lmstudio")
        if settings.xai_api_key:
            providers.append("grok")
        if settings.cerebras_api_key:
            providers.append("cerebras")
        if settings.sambanova_api_key:
            providers.append("sambanova")
        if getattr(settings, "mistral_api_key", None):
            providers.append("mistral")
        # Ollama is always available if base URL is set
        if settings.ollama_base_url:
            providers.append("ollama")

        return providers

    async def _fetch_provider_models(
        self, provider: str, force_refresh: bool = False
    ) -> list[ModelInfo]:
        """Fetch models from a specific provider."""
        provider = self._normalize_provider(provider)
        # Check cache first
        if (
            not force_refresh
            and provider in self._cache
            and self._cache[provider].is_valid()
        ):
            return self._cache[provider].models

        try:
            models = await self._fetch_models_impl(provider)
            self._cache[provider] = CachedModels(models=models, timestamp=time.time())
            return models
        except Exception as e:
            logger.error(f"Error fetching models from {provider}: {e}")
            # Return cached if available, even if stale
            if provider in self._cache:
                return self._cache[provider].models
            return []

    async def _fetch_models_impl(self, provider: str) -> list[ModelInfo]:
        """Implementation of model fetching per provider."""
        match provider:
            case "openrouter":
                return await self._fetch_openrouter_models()
            case "gemini":
                return await self._fetch_gemini_models()
            case "mistral":
                return await self._fetch_mistral_models()
            case "groq":
                return await self._fetch_groq_models()
            case "grok":
                return await self._fetch_grok_models()
            case "anthropic":
                return await self._fetch_anthropic_models()
            case "openai":
                return await self._fetch_openai_models()
            case "lmstudio":
                return await self._fetch_lmstudio_models()
            case "cerebras":
                return await self._fetch_cerebras_models()
            case "sambanova":
                return await self._fetch_sambanova_models()
            case "ollama":
                return await self._fetch_ollama_models()
            case _:
                return []

    async def _fetch_openrouter_models(self) -> list[ModelInfo]:
        """Fetch models from OpenRouter API."""
        client = await self._get_client()
        response = await client.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
        )
        response.raise_for_status()
        data = response.json()

        def _parse_price(value: Any) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        models = []
        for model in data.get("data", []):
            pricing = model.get("pricing", {})
            input_cost = _parse_price(pricing.get("prompt")) * 1_000_000
            output_cost = _parse_price(pricing.get("completion")) * 1_000_000
            # Free if both prompt and completion are 0 or "0"
            is_free = input_cost == 0.0 and output_cost == 0.0
            models.append(
                ModelInfo(
                    id=model["id"],
                    name=model.get("name", model["id"]),
                    provider="openrouter",
                    is_free=is_free,
                    input_cost_per_m=input_cost,
                    output_cost_per_m=output_cost,
                    context_length=model.get("context_length", 0),
                    description=model.get("description", ""),
                )
            )

        return models

    async def _fetch_gemini_models(self) -> list[ModelInfo]:
        """Fetch models from Google Gemini API (OpenAI-compatible endpoint)."""
        api_key = settings.google_api_key or settings.gemini_api_key
        if not api_key:
            return []

        client = await self._get_client()
        response = await client.get(
            "https://generativelanguage.googleapis.com/v1beta/openai/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        data = response.json()

        models = []
        for model in data.get("data", []):
            model_id = model.get("id")
            if not model_id:
                continue
            normalized_id = normalize_model_for_provider("gemini", model_id)
            if not normalized_id:
                continue
            models.append(
                ModelInfo(
                    id=normalized_id,
                    name=normalized_id,
                    provider="gemini",
                    is_free=False,
                    context_length=0,
                    description="",
                )
            )

        return models

    async def _fetch_mistral_models(self) -> list[ModelInfo]:
        """Fetch models from Mistral API."""
        api_key = getattr(settings, "mistral_api_key", None)
        if not api_key:
            return []

        client = await self._get_client()
        response = await client.get(
            "https://api.mistral.ai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        data = response.json()

        models = []
        for model in data.get("data", []):
            # Mistral free tier applies to all models with rate limits
            models.append(
                ModelInfo(
                    id=model["id"],
                    name=model.get("id", ""),
                    provider="mistral",
                    is_free=True,  # Free tier available
                    context_length=model.get("max_tokens", 0),
                    description=model.get("description", ""),
                )
            )

        return models

    async def _fetch_groq_models(self) -> list[ModelInfo]:
        """Fetch models from Groq API."""
        client = await self._get_client()
        response = await client.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
        )
        response.raise_for_status()
        data = response.json()

        models = []
        for model in data.get("data", []):
            models.append(
                ModelInfo(
                    id=model["id"],
                    name=model["id"],
                    provider="groq",
                    is_free=True,  # Groq is free with rate limits
                    context_length=model.get("context_window", 0),
                )
            )

        return models

    async def _fetch_grok_models(self) -> list[ModelInfo]:
        """Fetch models from xAI (Grok) API."""
        client = await self._get_client()
        response = await client.get(
            "https://api.x.ai/v1/models",
            headers={"Authorization": f"Bearer {settings.xai_api_key}"},
        )
        response.raise_for_status()
        data = response.json()

        models = []
        for model in data.get("data", []):
            model_id = model.get("id")
            if not model_id:
                continue
            models.append(
                ModelInfo(
                    id=model_id,
                    name=model.get("name", model_id),
                    provider="grok",
                    is_free=False,
                    context_length=model.get("context_window", 0)
                    or model.get("context_length", 0),
                    description=model.get("description", ""),
                )
            )

        return models

    async def _fetch_anthropic_models(self) -> list[ModelInfo]:
        """Fetch models from Anthropic API."""
        if not settings.anthropic_api_key:
            return []

        client = await self._get_client()
        response = await client.get(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        response.raise_for_status()
        data = response.json()

        models = []
        for model in data.get("data", []):
            model_id = model.get("id")
            if not model_id:
                continue
            models.append(
                ModelInfo(
                    id=model_id,
                    name=model.get("display_name", model_id),
                    provider="anthropic",
                    is_free=False,
                    context_length=0,
                    description="",
                )
            )

        return models

    async def _fetch_openai_models(self) -> list[ModelInfo]:
        """Fetch models from OpenAI or an OpenAI-compatible API."""
        client = await self._get_client()
        base_url = (os.getenv("OPENAI_BASE_URL") or settings.openai_base_url).rstrip(
            "/"
        )
        if not base_url:
            base_url = "https://api.openai.com/v1"
        api_key = os.getenv("OPENAI_API_KEY") or settings.openai_api_key
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        response = await client.get(
            f"{base_url}/models",
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

        models = []
        for model in data.get("data", []):
            model_id = model.get("id")
            if not model_id:
                continue
            models.append(
                ModelInfo(
                    id=model_id,
                    name=model.get("name", model_id),
                    provider="openai",
                    is_free=False,
                    context_length=model.get("context_window", 0)
                    or model.get("context_length", 0),
                )
            )

        return sorted(models, key=lambda item: item.id)

    async def _fetch_cerebras_models(self) -> list[ModelInfo]:
        """Fetch models from Cerebras API."""
        client = await self._get_client()
        response = await client.get(
            "https://api.cerebras.ai/v1/models",
            headers={"Authorization": f"Bearer {settings.cerebras_api_key}"},
        )
        response.raise_for_status()
        data = response.json()

        models = []
        for model in data.get("data", []):
            models.append(
                ModelInfo(
                    id=model["id"],
                    name=model["id"],
                    provider="cerebras",
                    is_free=True,  # 1M tokens/day free
                    context_length=model.get("context_window", 0),
                )
            )

        return models

    @staticmethod
    def _lmstudio_base_url() -> str:
        """Resolve LM Studio base URL from env/settings aliases."""
        return (
            os.getenv("LM_STUDIO_API_BASE")
            or os.getenv("LM_STUDIO_BASE_URL")
            or os.getenv("LMSTUDIO_BASE_URL")
            or settings.lmstudio_base_url
        )

    @staticmethod
    def _lmstudio_api_key() -> str:
        """Resolve optional LM Studio API key from env/settings aliases."""
        return resolve_lmstudio_api_key(
            os.getenv("LM_STUDIO_API_KEY"),
            os.getenv("LMSTUDIO_API_KEY"),
            settings.lmstudio_api_key,
        )

    async def _fetch_lmstudio_models(self) -> list[ModelInfo]:
        """Fetch models from local LM Studio OpenAI-compatible endpoint."""
        client = await self._get_client()
        base_url = self._lmstudio_base_url()
        api_key = self._lmstudio_api_key()
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        endpoints = lmstudio_model_endpoints(base_url)
        last_error: Exception | None = None
        for endpoint in endpoints:
            try:
                response = await client.get(endpoint, headers=headers)
                response.raise_for_status()
                data = response.json()

                if isinstance(data, dict):
                    items = data.get("data", [])
                elif isinstance(data, list):
                    items = data
                else:
                    items = []

                models: list[ModelInfo] = []
                for item in items:
                    model_id = item.get("id") or item.get("name")
                    if not model_id:
                        continue
                    normalized_id = normalize_model_for_provider("lmstudio", model_id)
                    if not normalized_id:
                        continue
                    models.append(
                        ModelInfo(
                            id=normalized_id,
                            name=normalized_id,
                            provider="lmstudio",
                            is_free=True,
                            context_length=0,
                        )
                    )
                if models:
                    return models
            except Exception as exc:
                last_error = exc
                continue

        if last_error:
            logger.warning(f"LM Studio not available: {last_error}")
        return []

    async def _fetch_sambanova_models(self) -> list[ModelInfo]:
        """Fetch models from SambaNova API.

        NOTE: Context7 docs unavailable at implementation time; endpoint is best-effort.
        """
        client = await self._get_client()
        response = await client.get(
            "https://api.sambanova.ai/v1/models",
            headers={"Authorization": f"Bearer {settings.sambanova_api_key}"},
        )
        response.raise_for_status()
        data = response.json()

        models = []
        for model in data.get("data", []):
            model_id = model.get("id")
            if not model_id:
                continue
            models.append(
                ModelInfo(
                    id=model_id,
                    name=model.get("name", model_id),
                    provider="sambanova",
                    is_free=False,
                    context_length=model.get("context_window", 0)
                    or model.get("context_length", 0),
                    description=model.get("description", ""),
                )
            )

        return models

    async def _fetch_ollama_models(self) -> list[ModelInfo]:
        """Fetch models from local Ollama."""
        client = await self._get_client()
        base_url = settings.ollama_base_url.rstrip("/")
        try:
            response = await client.get(f"{base_url}/api/tags")
            response.raise_for_status()
            data = response.json()

            models = []
            for model in data.get("models", []):
                models.append(
                    ModelInfo(
                        id=model["name"],
                        name=model["name"],
                        provider="ollama",
                        is_free=True,  # Local is always free
                        context_length=0,
                    )
                )

            return models
        except Exception as e:
            logger.warning(f"Ollama not available: {e}")
            return []


# Global registry instance
_registry: ModelRegistry | None = None


def get_model_registry() -> ModelRegistry:
    """Get global model registry instance."""
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry


async def close_model_registry() -> None:
    """Close the global model registry client without creating a new registry."""
    global _registry
    if _registry is None:
        return
    await _registry.close()
    _registry = None
