from src.core.llm_provider_docker import LLMProvider, LLMRouter
from src.core.model_normalization import (
    normalize_model_for_provider,
    normalize_provider_name,
)


def test_normalize_gemini_models_prefix():
    assert (
        normalize_model_for_provider("gemini", "models/gemini-2.0-flash")
        == "gemini-2.0-flash"
    )


def test_normalize_gemini_provider_prefix():
    assert (
        normalize_model_for_provider("gemini", "gemini/gemini-2.0-flash")
        == "gemini-2.0-flash"
    )


def test_preserve_groq_openai_namespace_model():
    assert (
        normalize_model_for_provider("groq", "openai/gpt-oss-120b")
        == "openai/gpt-oss-120b"
    )


def test_provider_prefix_dedupe_matches_selected_provider_only():
    assert (
        normalize_model_for_provider("openrouter", "openrouter/meta-llama/llama-3.1")
        == "meta-llama/llama-3.1"
    )
    assert (
        normalize_model_for_provider("groq", "openrouter/meta-llama/llama-3.1")
        == "openrouter/meta-llama/llama-3.1"
    )


def test_provider_alias_normalization():
    assert normalize_provider_name("xai") == "grok"


def test_router_builds_canonical_gemini_model_string():
    router = object.__new__(LLMRouter)
    router.provider = LLMProvider.GEMINI
    router.model = "models/gemini-2.0-flash"

    assert router._build_model_string() == "gemini/gemini-2.0-flash"


def test_router_forces_gpt5_temperature_to_litellm_safe_value():
    router = object.__new__(LLMRouter)
    router.provider = LLMProvider.OPENAI
    router.model = "gpt-5.3-codex"
    router.temperature_override = None

    assert router._chat_completion_temperature(0) == 1.0


def test_router_preserves_non_gpt5_zero_temperature():
    router = object.__new__(LLMRouter)
    router.provider = LLMProvider.OPENAI
    router.model = "gpt-4o-mini"
    router.temperature_override = None

    assert router._chat_completion_temperature(0) == 0
