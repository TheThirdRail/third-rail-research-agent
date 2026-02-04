"""Service for fetching available LLM models and pricing."""

import logging
from typing import Any

import httpx
from litellm import model_cost
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ModelInfo(BaseModel):
    """Model information with pricing."""

    id: str
    name: str
    provider: str
    input_cost_per_m: float = 0.0
    output_cost_per_m: float = 0.0
    label: str  # Pre-formatted "Name - $0.15/$0.60"


class ModelService:
    """Service to fetch models from various sources."""

    def __init__(self) -> None:
        """Initialize service."""
        pass

    async def get_models(self, provider: str) -> list[ModelInfo]:
        """Get models for a specific provider."""
        provider = provider.lower()

        try:
            if provider == "openrouter":
                return await self._fetch_openrouter()
            elif provider == "ollama":
                return await self._fetch_ollama()
            else:
                return self._fetch_litellm(provider)
        except Exception as e:
            logger.error(f"Failed to fetch models for {provider}: {e}")
            return []

    async def _fetch_openrouter(self) -> list[ModelInfo]:
        """Fetch models from OpenRouter API."""
        async with httpx.AsyncClient() as client:
            response = await client.get("https://openrouter.ai/api/v1/models")
            response.raise_for_status()
            data = response.json()

        models = []
        for item in data.get("data", []):
            # Pricing is per token usually, we want per Million
            # OpenRouter gives 'prompt' and 'completion' pricing
            pricing = item.get("pricing", {})
            input_cost = float(pricing.get("prompt", 0)) * 1_000_000
            output_cost = float(pricing.get("completion", 0)) * 1_000_000

            # Format label
            label = f"{item['name']} - ${input_cost:.2f}/${output_cost:.2f} (per 1M)"

            models.append(
                ModelInfo(
                    id=item["id"],
                    name=item["name"],
                    provider="openrouter",
                    input_cost_per_m=input_cost,
                    output_cost_per_m=output_cost,
                    label=label,
                )
            )

        # Sort by name
        return sorted(models, key=lambda x: x.name)

    async def _fetch_ollama(self) -> list[ModelInfo]:
        """Fetch models from local Ollama instance."""
        # Try docker internal DNS first, fallback to localhost if running locally
        urls = ["http://ollama:11434/api/tags", "http://localhost:11434/api/tags"]

        data: dict[str, Any] = {}

        async with httpx.AsyncClient(timeout=2.0) as client:
            for url in urls:
                try:
                    response = await client.get(url)
                    if response.status_code == 200:
                        data = response.json()
                        break
                except Exception:
                    continue

        if not data:
            logger.warning("Could not connect to Ollama")
            return []

        models = []
        for model in data.get("models", []):
            name = model["name"]
            # Ollama is free (local compute)
            label = f"{name} - Free (Local)"

            models.append(
                ModelInfo(
                    id=name,
                    name=name,
                    provider="ollama",
                    input_cost_per_m=0.0,
                    output_cost_per_m=0.0,
                    label=label,
                )
            )

        return sorted(models, key=lambda x: x.name)

    def _fetch_litellm(self, provider: str) -> list[ModelInfo]:
        """Fetch models from LiteLLM internal database."""
        models = []

        # litellm.model_cost keys are like 'gpt-4', 'claude-3-opus-20240229'
        # We need to filter by provider heuristically or use known prefixes

        # Map our provider names to LiteLLM prefixes/keys
        provider_map = {
            "openai": ["gpt-", "dall-e", "text-embedding"],
            "anthropic": ["claude-"],
            "gemini": ["gemini-"],
            "groq": ["groq/"],  # LiteLLM often prefixes non-openai with provider/
            "mistral": ["mistral/"],
            "cerebras": ["cerebras/"],
            "sambanova": ["sambanova/"],
            "xai": ["xai/"],
        }

        prefixes = provider_map.get(provider, [])
        if not prefixes and provider not in ["ollama", "openrouter"]:
            # If unknown provider, try to match broadly or return all?
            # Better to return empty than junk
            return []

        for model_id, info in model_cost.items():
            # Check if model belongs to provider
            # LiteLLM keys are messy. Some are 'gpt-4', some 'vertex_ai/gemini-pro'

            is_match = False
            for prefix in prefixes:
                if model_id.startswith(prefix) or f"/{prefix}" in model_id:
                    is_match = True
                    break

            # Special logic for simple providers like 'openai' checking mostly standard keys
            if provider == "openai" and "gpt" in model_id and "/" not in model_id:
                is_match = True

            if is_match:
                input_cost = info.get("input_cost_per_token", 0) * 1_000_000
                output_cost = info.get("output_cost_per_token", 0) * 1_000_000

                label = f"{model_id} - ${input_cost:.2f}/${output_cost:.2f}"

                models.append(
                    ModelInfo(
                        id=model_id,
                        name=model_id,
                        provider=provider,
                        input_cost_per_m=input_cost,
                        output_cost_per_m=output_cost,
                        label=label,
                    )
                )

        return sorted(models, key=lambda x: x.name)
