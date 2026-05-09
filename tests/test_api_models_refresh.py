from fastapi.testclient import TestClient

from src.api.main import app
from src.services import model_service

TEST_ADMIN_KEY = "test-secret-key-for-ci"


def _set_admin_key(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_API_KEY", TEST_ADMIN_KEY)
    from src.core import config as _cfg

    _cfg.get_settings.cache_clear()
    _cfg.settings = _cfg.get_settings()


def _admin_headers() -> dict[str, str]:
    return {"X-Research-Agent-Key": TEST_ADMIN_KEY}


def test_models_refresh_requires_key(monkeypatch):
    _set_admin_key(monkeypatch)

    client = TestClient(app)
    response = client.get("/api/models?provider=openrouter&refresh=true")

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized."


def test_models_refresh_param_with_key(monkeypatch):
    _set_admin_key(monkeypatch)
    called = {}

    async def fake_get_models(self, provider: str, refresh: bool = False):
        called["refresh"] = refresh
        return []

    monkeypatch.setattr(model_service.ModelService, "get_models", fake_get_models)

    client = TestClient(app)
    response = client.get(
        "/api/models?provider=openrouter&refresh=true",
        headers=_admin_headers(),
    )

    assert response.status_code == 200
    assert called.get("refresh") is True
