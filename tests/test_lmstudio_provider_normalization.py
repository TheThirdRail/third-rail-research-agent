from src.core.llm_provider_docker import LLMProvider, LLMRouter
from src.core.model_normalization import (
    normalize_model_for_provider,
    normalize_provider_name,
)


def test_normalize_lmstudio_provider_aliases():
    assert normalize_provider_name("lm_studio") == "lmstudio"
    assert normalize_provider_name("LM-STUDIO") == "lmstudio"


def test_normalize_lmstudio_model_prefixes():
    assert (
        normalize_model_for_provider("lmstudio", "lm_studio/qwen2.5-7b-instruct")
        == "qwen2.5-7b-instruct"
    )
    assert (
        normalize_model_for_provider("lmstudio", "lmstudio/qwen2.5-7b-instruct")
        == "qwen2.5-7b-instruct"
    )


def test_router_builds_lmstudio_model_string():
    router = object.__new__(LLMRouter)
    router.provider = LLMProvider.LMSTUDIO
    router.model = "lm_studio/qwen2.5-7b-instruct"

    assert router._build_model_string() == "lm_studio/qwen2.5-7b-instruct"
