"""Service for fetching available LLM models."""

import logging

from pydantic import BaseModel

from src.core.config import settings
from src.core.model_registry import ModelInfo as RegistryModelInfo
from src.core.model_registry import get_model_registry

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

    OPENAI_FALLBACK_MODELS = (
        "gpt-5.3-codex",
        "gpt-5.5",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.4-nano",
    )

    def __init__(self) -> None:
        """Initialize service."""
        pass

    async def get_models(self, provider: str, refresh: bool = False) -> list[ModelInfo]:
        """Get models for a specific provider."""
        provider = provider.lower()
        provider_alias = "grok" if provider in {"xai", "grok"} else provider
        registry = get_model_registry()

        try:
            models = await registry.list_models(provider_alias, force_refresh=refresh)
        except Exception as e:
            logger.error(f"Failed to fetch models for {provider}: {e}")
            models = []

        if provider_alias == "openai" and not models:
            models = self._fallback_openai_models()
        return [self._to_model_info(model) for model in models]

    @classmethod
    def _fallback_openai_models(cls) -> list[RegistryModelInfo]:
        """Current OpenAI/Codex model IDs when live discovery is unavailable."""
        model_ids = list(cls.OPENAI_FALLBACK_MODELS)
        selected = settings.selected_model.strip()
        selected_is_openai_like = selected.startswith(("gpt-", "o"))
        if selected and selected_is_openai_like and selected not in model_ids:
            model_ids.insert(0, selected)
        return [
            RegistryModelInfo(id=model_id, name=model_id, provider="openai")
            for model_id in model_ids
        ]

    @staticmethod
    def _to_model_info(model: RegistryModelInfo) -> ModelInfo:
        """Map registry model to API response model."""
        display_name = model.name or model.id
        if model.provider == "openrouter":
            input_cost = model.input_cost_per_m or 0.0
            output_cost = model.output_cost_per_m or 0.0
            if input_cost == 0.0 and output_cost == 0.0:
                label = f"{display_name} — Free"
            else:
                def _fmt(cost: float) -> str:
                    formatted = f"{cost:.4f}".rstrip("0").rstrip(".")
                    return formatted or "0"
                label = (
                    f"{display_name} — ${_fmt(input_cost)}/${_fmt(output_cost)} "
                    "per 1M (prompt/completion)"
                )
        else:
            label = display_name
        return ModelInfo(
            id=model.id,
            name=model.name,
            provider=model.provider,
            input_cost_per_m=model.input_cost_per_m if model.provider == "openrouter" else 0.0,
            output_cost_per_m=model.output_cost_per_m if model.provider == "openrouter" else 0.0,
            label=label,
        )
