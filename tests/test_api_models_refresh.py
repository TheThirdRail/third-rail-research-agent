from fastapi.testclient import TestClient

from src.api.main import app
from src.services import model_service


def test_models_refresh_param(monkeypatch):
    called = {}

    async def fake_get_models(self, provider: str, refresh: bool = False):
        called["refresh"] = refresh
        return []

    monkeypatch.setattr(model_service.ModelService, "get_models", fake_get_models)

    client = TestClient(app)
    response = client.get("/api/models?provider=openrouter&refresh=true")

    assert response.status_code == 200
    assert called.get("refresh") is True
