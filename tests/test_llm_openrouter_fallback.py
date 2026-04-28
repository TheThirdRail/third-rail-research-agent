from src.core.llm_provider_docker import FALLBACK_MODELS, LLMProvider


def test_openrouter_fallback_model_is_non_obsolete():
    assert FALLBACK_MODELS[LLMProvider.OPENROUTER] == "openrouter/free"
