"""Model Registry - Dynamic model fetching from LLM providers."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from src.core.config import settings

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
    context_length: int = 0
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "is_free": self.is_free,
            "context_length": self.context_length,
            "description": self.description,
            "display_name": f"{self.name} (Free)" if self.is_free else self.name,
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

    async def list_models(self, provider: str | None = None) -> list[ModelInfo]:
        """List all available models, optionally filtered by provider.

        Args:
            provider: Filter to specific provider, or None for all

        Returns:
            List of available models
        """
        if provider:
            return await self._fetch_provider_models(provider)

        # Fetch from all configured providers
        all_models: list[ModelInfo] = []
        providers = self._get_configured_providers()

        tasks = [self._fetch_provider_models(p) for p in providers]
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

    async def _fetch_provider_models(self, provider: str) -> list[ModelInfo]:
        """Fetch models from a specific provider."""
        # Check cache first
        if provider in self._cache and self._cache[provider].is_valid():
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
            case "anthropic":
                return self._get_anthropic_models()
            case "openai":
                return await self._fetch_openai_models()
            case "cerebras":
                return await self._fetch_cerebras_models()
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

        models = []
        for model in data.get("data", []):
            pricing = model.get("pricing", {})
            # Free if both prompt and completion are 0 or "0"
            is_free = (
                str(pricing.get("prompt", "1")) == "0"
                and str(pricing.get("completion", "1")) == "0"
            )
            models.append(
                ModelInfo(
                    id=model["id"],
                    name=model.get("name", model["id"]),
                    provider="openrouter",
                    is_free=is_free,
                    context_length=model.get("context_length", 0),
                    description=model.get("description", ""),
                )
            )

        return models

    async def _fetch_gemini_models(self) -> list[ModelInfo]:
        """Fetch models from Google Gemini API."""
        client = await self._get_client()
        response = await client.get(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={settings.google_api_key}"
        )
        response.raise_for_status()
        data = response.json()

        models = []
        for model in data.get("models", []):
            name = model.get("name", "").replace("models/", "")
            # All Gemini API models are free tier with rate limits
            models.append(
                ModelInfo(
                    id=name,
                    name=model.get("displayName", name),
                    provider="gemini",
                    is_free=True,  # Gemini API is free with rate limits
                    context_length=model.get("inputTokenLimit", 0),
                    description=model.get("description", ""),
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

    def _get_anthropic_models(self) -> list[ModelInfo]:
        """Get Anthropic models (no list API, hardcoded)."""
        # Anthropic doesn't have a models list API
        return [
            ModelInfo(
                id="claude-3-5-sonnet-20241022",
                name="Claude 3.5 Sonnet",
                provider="anthropic",
                is_free=False,
                context_length=200000,
            ),
            ModelInfo(
                id="claude-3-5-haiku-20241022",
                name="Claude 3.5 Haiku",
                provider="anthropic",
                is_free=False,
                context_length=200000,
            ),
            ModelInfo(
                id="claude-3-opus-20240229",
                name="Claude 3 Opus",
                provider="anthropic",
                is_free=False,
                context_length=200000,
            ),
        ]

    async def _fetch_openai_models(self) -> list[ModelInfo]:
        """Fetch models from OpenAI API."""
        client = await self._get_client()
        response = await client.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        )
        response.raise_for_status()
        data = response.json()

        # Filter to useful models
        allowed_prefixes = ("gpt-4", "gpt-3.5", "o1", "o3")
        models = []
        for model in data.get("data", []):
            model_id = model["id"]
            if any(model_id.startswith(p) for p in allowed_prefixes):
                models.append(
                    ModelInfo(
                        id=model_id,
                        name=model_id,
                        provider="openai",
                        is_free=False,
                        context_length=0,
                    )
                )

        return models

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
