import os

os.environ["DEBUG"] = "true"

from src.agents import config as agents_config
from src.core.llm_provider_docker import LLMProvider
from src.core.token_usage_context import token_usage_run


class _FakeRouter:
    def __init__(
        self,
        provider: str,
        reasoning_effort: str | None = None,
        model: str | None = None,
    ):
        self.provider = LLMProvider(provider)
        self.temperature_override = None
        self.reasoning_effort = reasoning_effort
        self.model = model or f"{self.provider.value}/model-a"

    def get_crewai_config(self):
        config = {
            "model": self.model,
            "api_key": "test-key",
            "base_url": "http://provider.test/v1",
        }
        if self.reasoning_effort:
            config["reasoning_effort"] = self.reasoning_effort
        return config


def test_build_crewai_llm_includes_api_base_and_fallbacks(monkeypatch):
    monkeypatch.setattr(
        agents_config,
        "get_llm_router",
        lambda agent_name=None: _FakeRouter("sambanova"),
    )
    monkeypatch.setattr(
        agents_config.settings,
        "lmstudio_fallback_enabled",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        agents_config.settings,
        "lmstudio_fallback_model",
        "lm_studio/qwen2.5-7b-instruct",
        raising=False,
    )

    llm = agents_config.build_crewai_llm("source_aggregator")

    assert llm.model == "sambanova/model-a"
    assert llm.api_key == "test-key"
    assert llm.base_url == "http://provider.test/v1"
    assert llm.api_base == "http://provider.test/v1"
    assert llm.additional_params.get("fallbacks") == ["lm_studio/qwen2.5-7b-instruct"]


def test_build_crewai_llm_uses_native_openai_retry_without_litellm_params(
    monkeypatch,
):
    monkeypatch.setattr(
        agents_config,
        "get_llm_router",
        lambda agent_name=None: _FakeRouter("openai", model="openai/gpt-5.4-mini"),
    )
    monkeypatch.setattr(
        agents_config.settings,
        "lmstudio_fallback_enabled",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        agents_config.settings,
        "lmstudio_fallback_model",
        "lm_studio/qwen2.5-7b-instruct",
        raising=False,
    )

    llm = agents_config.build_crewai_llm("source_aggregator")

    assert llm.model == "gpt-5.4-mini"
    assert llm.max_retries == 2
    assert "num_retries" not in llm.additional_params
    assert "fallbacks" not in llm.additional_params


def test_build_crewai_llm_skips_lmstudio_fallback_when_primary_is_lmstudio(monkeypatch):
    monkeypatch.setattr(
        agents_config,
        "get_llm_router",
        lambda agent_name=None: _FakeRouter("lmstudio"),
    )
    monkeypatch.setattr(
        agents_config.settings,
        "lmstudio_fallback_enabled",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        agents_config.settings,
        "lmstudio_fallback_model",
        "qwen2.5-7b-instruct",
        raising=False,
    )

    llm = agents_config.build_crewai_llm("source_aggregator")

    assert llm.model == "lmstudio/model-a"
    assert llm.additional_params.get("fallbacks") is None


def test_build_crewai_llm_passes_reasoning_effort(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeLLM:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        agents_config,
        "get_llm_router",
        lambda agent_name=None: _FakeRouter("openai", reasoning_effort="high"),
    )
    monkeypatch.setattr(agents_config, "LLM", _FakeLLM)

    agents_config.build_crewai_llm("source_aggregator")

    assert captured["reasoning_effort"] == "high"


def test_build_crewai_llm_passes_token_usage_metadata(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeLLM:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        agents_config,
        "get_llm_router",
        lambda agent_name=None: _FakeRouter("openai", model="openai/gpt-5.4"),
    )
    monkeypatch.setattr(agents_config, "LLM", _FakeLLM)

    with token_usage_run("0001 - Trump China deal Xi", "Trump China deal Xi"):
        agents_config.build_crewai_llm("profile_reader")

    assert captured["extra_body"] == {
        "metadata": {
            "run_id": "0001 - Trump China deal Xi",
            "run_text": "Trump China deal Xi",
            "agent_name": "PROFILE_READER",
        }
    }
