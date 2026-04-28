import pytest

from src.core.config import settings
from src.core.model_registry import ModelRegistry


class DummyResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class DummyClient:
    def __init__(self, payload: dict):
        self._payload = payload
        self.calls: list[dict] = []

    async def get(self, url: str, headers: dict | None = None):
        self.calls.append({"url": url, "headers": headers})
        return DummyResponse(self._payload)


@pytest.mark.asyncio
async def test_gemini_openai_models_endpoint(monkeypatch):
    registry = ModelRegistry()
    dummy = DummyClient({"data": [{"id": "models/gemini-3-flash"}]})

    async def fake_get_client():
        return dummy

    monkeypatch.setattr(registry, "_get_client", fake_get_client)
    monkeypatch.setattr(settings, "google_api_key", "test-key", raising=False)

    models = await registry._fetch_gemini_models()

    assert dummy.calls[0]["url"].endswith("/v1beta/openai/models")
    assert dummy.calls[0]["headers"]["Authorization"] == "Bearer test-key"
    assert len(models) == 1
    assert models[0].id == "gemini-3-flash"
