import asyncio
import os
from types import SimpleNamespace

os.environ["DEBUG"] = "true"

import src.core.llm_provider_docker as llm_module


class _FakeBudget:
    def can_afford(self, _model_is_free: bool) -> bool:
        return True

    def get_status(self) -> dict[str, float]:
        return {"current_spend": 0.0, "limit": 1.0}

    def track_spend(self, _cost: float) -> None:
        return None


def test_complete_recovers_once_after_openrouter_not_found(monkeypatch):
    router = object.__new__(llm_module.LLMRouter)
    router.provider = llm_module.LLMProvider.OPENROUTER
    router.model = "meta-llama/llama-3.2-11b-vision-instruct:free"
    router.litellm_model = "openrouter/meta-llama/llama-3.2-11b-vision-instruct:free"
    router.api_key = "test-key"
    router.base_url = "https://openrouter.ai/api/v1"
    router.temperature_override = None
    router.free_tier = False
    router.reasoning_effort = None

    attempts = {"count": 0, "models": []}

    def fake_completion(**kwargs):
        attempts["count"] += 1
        attempts["models"].append(kwargs["model"])
        if attempts["count"] == 1:
            raise Exception(
                'NotFoundError: OpenrouterException - {"error":{"message":"No endpoints found for model","code":404}}'
            )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )

    def fake_recover(exc: Exception) -> bool:
        assert "no endpoints found" in str(exc).lower()
        router._set_runtime_model("openrouter/free")
        return True

    monkeypatch.setattr(llm_module, "completion", fake_completion)
    monkeypatch.setattr(llm_module, "completion_cost", lambda completion_response: 0.0)
    monkeypatch.setattr(llm_module, "get_budget_service", lambda: _FakeBudget())
    monkeypatch.setattr(router, "_recover_openrouter_model_sync", fake_recover)

    output = router.complete([{"role": "user", "content": "hello"}])

    assert output == "ok"
    assert attempts["count"] == 2
    assert attempts["models"][0] == "openrouter/meta-llama/llama-3.2-11b-vision-instruct:free"
    assert attempts["models"][1] == "openrouter/free"


def _build_openai_router(reasoning_effort: str | None):
    router = object.__new__(llm_module.LLMRouter)
    router.provider = llm_module.LLMProvider.OPENAI
    router.model = "gpt-5.4"
    router.litellm_model = "openai/gpt-5.4"
    router.api_key = "test-key"
    router.base_url = "https://api.openai.com/v1"
    router.temperature_override = None
    router.free_tier = False
    router.reasoning_effort = reasoning_effort
    return router


def test_complete_passes_supported_openai_reasoning_effort(monkeypatch):
    router = _build_openai_router("high")
    captured: dict[str, object] = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )

    monkeypatch.setattr(llm_module, "completion", fake_completion)
    monkeypatch.setattr(llm_module, "completion_cost", lambda completion_response: 0.0)
    monkeypatch.setattr(llm_module, "get_budget_service", lambda: _FakeBudget())

    assert router.complete([{"role": "user", "content": "hello"}]) == "ok"
    assert captured["reasoning_effort"] == "high"


def test_complete_omits_openai_reasoning_effort_none(monkeypatch):
    router = _build_openai_router("none")
    captured: dict[str, object] = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )

    monkeypatch.setattr(llm_module, "completion", fake_completion)
    monkeypatch.setattr(llm_module, "completion_cost", lambda completion_response: 0.0)
    monkeypatch.setattr(llm_module, "get_budget_service", lambda: _FakeBudget())

    assert router.complete([{"role": "user", "content": "hello"}]) == "ok"
    assert "reasoning_effort" not in captured


def test_acomplete_passes_supported_openai_reasoning_effort(monkeypatch):
    router = _build_openai_router("medium")
    captured: dict[str, object] = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )

    monkeypatch.setattr(llm_module, "acompletion", fake_acompletion)
    monkeypatch.setattr(llm_module, "completion_cost", lambda completion_response: 0.0)
    monkeypatch.setattr(llm_module, "get_budget_service", lambda: _FakeBudget())

    output = asyncio.run(router.acomplete([{"role": "user", "content": "hello"}]))

    assert output == "ok"
    assert captured["reasoning_effort"] == "medium"
