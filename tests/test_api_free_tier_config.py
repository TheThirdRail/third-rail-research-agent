import os
from types import SimpleNamespace

os.environ["DEBUG"] = "true"

from fastapi.testclient import TestClient

from src.api.main import app
from src.services.agent_config_service import AgentConfigService


def test_update_agent_config_free_tier(monkeypatch):
    def fake_get_config(self, agent_name: str):
        return None

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

    client = TestClient(app)
    response = client.post(
        "/api/agents/profile_reader/config", json={"free_tier": True}
    )

    assert response.status_code == 200
    assert response.json()["config"]["free_tier"] is True
