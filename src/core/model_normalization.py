"""Helpers for provider/model identifier normalization."""

from __future__ import annotations


def normalize_provider_name(provider: str | None) -> str | None:
    """Normalize provider aliases to canonical provider names."""
    if provider is None:
        return None
    normalized = provider.strip().lower()
    if normalized == "xai":
        return "grok"
    if normalized in {"lm_studio", "lm-studio"}:
        return "lmstudio"
    return normalized


def normalize_model_for_provider(provider: str | None, model: str | None) -> str:
    """Normalize model identifiers for a given provider.

    Rules:
    - trim whitespace
    - remove matching provider prefix (for example `gemini/`)
    - for Gemini, strip leading `models/`
    - preserve non-matching slash-based model IDs (for example Groq's `openai/gpt-*`)
    """
    if model is None:
        return ""

    normalized_model = model.strip()
    if not normalized_model:
        return normalized_model

    normalized_provider = normalize_provider_name(provider)
    if not normalized_provider:
        return normalized_model

    provider_prefixes = {
        "openrouter": {"openrouter"},
        "gemini": {"gemini"},
        "anthropic": {"anthropic"},
        "groq": {"groq"},
        "openai": {"openai"},
        "grok": {"grok", "xai"},
        "cerebras": {"cerebras"},
        "sambanova": {"sambanova"},
        "mistral": {"mistral"},
        "lmstudio": {"lmstudio", "lm_studio"},
        "ollama": {"ollama"},
    }

    prefixes = provider_prefixes.get(normalized_provider, set())
    lower_model = normalized_model.lower()

    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            marker = f"{prefix}/"
            if lower_model.startswith(marker):
                normalized_model = normalized_model[len(marker) :]
                lower_model = normalized_model.lower()
                changed = True
                break

    if normalized_provider == "gemini":
        while lower_model.startswith("models/"):
            normalized_model = normalized_model[len("models/") :]
            lower_model = normalized_model.lower()

    return normalized_model
