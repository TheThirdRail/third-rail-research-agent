import os
from types import SimpleNamespace

os.environ["DEBUG"] = "true"

from fastapi.testclient import TestClient

from src.api.main import app
from src.services.agent_config_service import AgentConfigService


class _FakeModelService:
    def __init__(self, ids: list[str]):
        self.ids = ids

    async def get_models(self, provider: str, refresh: bool = False):
        assert provider in {"gemini", "openai"}
        return [SimpleNamespace(id=model_id) for model_id in self.ids]


def test_update_agent_config_normalizes_gemini_model(monkeypatch):
    captured: dict[str, str | None] = {}

    def fake_get_config(self, agent_name: str):
        return SimpleNamespace(
            provider="gemini",
            model="gemini-2.0-flash",
            temperature=None,
            budget_limit=None,
            free_tier=True,
            reasoning_effort=None,
        )

    def fake_set_config(
        self,
        agent_name: str,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        budget_limit: float | None = None,
        free_tier: bool | None = None,
        reasoning_effort: str | None = None,
        clear_reasoning_effort: bool = False,
    ):
        captured["provider"] = provider
        captured["model"] = model
        captured["reasoning_effort"] = reasoning_effort
        captured["clear_reasoning_effort"] = clear_reasoning_effort
        return SimpleNamespace(
            provider=provider,
            model=model,
            temperature=temperature,
            budget_limit=budget_limit,
            free_tier=free_tier,
            reasoning_effort=reasoning_effort,
        )

    monkeypatch.setattr(AgentConfigService, "get_config", fake_get_config)
    monkeypatch.setattr(AgentConfigService, "set_config", fake_set_config)
    monkeypatch.setattr(
        "src.api.routes.agents.ModelService",
        lambda: _FakeModelService(["gemini-2.0-flash"]),
    )

    client = TestClient(app)
    response = client.post(
        "/api/agents/bias_classifier/config",
        json={"provider": "gemini", "model": "models/gemini-2.0-flash"},
    )

    assert response.status_code == 200
    assert response.json()["config"]["model"] == "gemini-2.0-flash"
    assert captured["provider"] == "gemini"
    assert captured["model"] == "gemini-2.0-flash"


def test_update_agent_config_saves_openai_fallback_model(monkeypatch):
    captured: dict[str, str | bool | None] = {}

    def fake_get_config(self, agent_name: str):
        return SimpleNamespace(
            provider="openai",
            model="gpt-5.4",
            temperature=None,
            budget_limit=None,
            free_tier=False,
            reasoning_effort=None,
        )

    def fake_set_config(
        self,
        agent_name: str,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        budget_limit: float | None = None,
        free_tier: bool | None = None,
        reasoning_effort: str | None = None,
        clear_reasoning_effort: bool = False,
    ):
        captured["provider"] = provider
        captured["model"] = model
        captured["reasoning_effort"] = reasoning_effort
        return SimpleNamespace(
            provider=provider,
            model=model,
            temperature=temperature,
            budget_limit=budget_limit,
            free_tier=free_tier,
            reasoning_effort=reasoning_effort,
        )

    monkeypatch.setattr(AgentConfigService, "get_config", fake_get_config)
    monkeypatch.setattr(AgentConfigService, "set_config", fake_set_config)
    monkeypatch.setattr(
        "src.api.routes.agents.ModelService",
        lambda: _FakeModelService(["gpt-5.4"]),
    )

    client = TestClient(app)
    response = client.post(
        "/api/agents/bias_classifier/config",
        json={
            "provider": "openai",
            "model": "gpt-5.4",
            "reasoning_effort": "high",
        },
    )

    assert response.status_code == 200
    assert response.json()["config"]["model"] == "gpt-5.4"
    assert response.json()["config"]["reasoning_effort"] == "high"
    assert captured["provider"] == "openai"
    assert captured["model"] == "gpt-5.4"
    assert captured["reasoning_effort"] == "high"


def test_update_agent_config_rejects_invalid_openai_model(monkeypatch):
    def fake_get_config(self, agent_name: str):
        return SimpleNamespace(
            provider="openai",
            model="gpt-5.4",
            temperature=None,
            budget_limit=None,
            free_tier=False,
            reasoning_effort=None,
        )

    monkeypatch.setattr(AgentConfigService, "get_config", fake_get_config)
    monkeypatch.setattr(
        "src.api.routes.agents.ModelService",
        lambda: _FakeModelService(["gpt-5.4"]),
    )

    client = TestClient(app)
    response = client.post(
        "/api/agents/bias_classifier/config",
        json={"provider": "openai", "model": "not-a-real-model"},
    )

    assert response.status_code == 400
    assert "Invalid model" in response.json()["detail"]


def test_update_agent_config_clears_reasoning_when_provider_changes(monkeypatch):
    captured: dict[str, str | bool | None] = {}

    def fake_get_config(self, agent_name: str):
        return SimpleNamespace(
            provider="openai",
            model="gpt-5.4",
            temperature=None,
            budget_limit=None,
            free_tier=False,
            reasoning_effort="high",
        )

    def fake_set_config(
        self,
        agent_name: str,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        budget_limit: float | None = None,
        free_tier: bool | None = None,
        reasoning_effort: str | None = None,
        clear_reasoning_effort: bool = False,
    ):
        captured["reasoning_effort"] = reasoning_effort
        captured["clear_reasoning_effort"] = clear_reasoning_effort
        return SimpleNamespace(
            provider=provider,
            model=model,
            temperature=temperature,
            budget_limit=budget_limit,
            free_tier=free_tier,
            reasoning_effort=None if clear_reasoning_effort else reasoning_effort,
        )

    monkeypatch.setattr(AgentConfigService, "get_config", fake_get_config)
    monkeypatch.setattr(AgentConfigService, "set_config", fake_set_config)

    client = TestClient(app)
    response = client.post(
        "/api/agents/bias_classifier/config",
        json={"provider": "gemini", "reasoning_effort": None},
    )

    assert response.status_code == 200
    assert response.json()["config"]["reasoning_effort"] is None
    assert captured["reasoning_effort"] is None
    assert captured["clear_reasoning_effort"] is True
