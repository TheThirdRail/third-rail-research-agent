import os

os.environ["DEBUG"] = "true"

from src.core.model_registry import ModelRegistry


class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class _FakeClient:
    def __init__(self):
        self.calls = []

    async def get(self, url, headers=None):
        self.calls.append({"url": url, "headers": headers or {}})
        return _FakeResponse(
            {
                "data": [
                    {"id": "gpt-5.1"},
                    {"id": "o4-mini"},
                    {"id": "bridge/custom-model", "name": "Bridge Custom"},
                    {"name": "missing-id"},
                ]
            }
        )


async def test_fetch_openai_models_uses_configured_base_url(monkeypatch):
    registry = ModelRegistry()
    client = _FakeClient()

    async def fake_get_client():
        return client

    monkeypatch.setattr(registry, "_get_client", fake_get_client)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:8790/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "local-placeholder")

    models = await registry._fetch_openai_models()

    assert client.calls == [
        {
            "url": "http://127.0.0.1:8790/v1/models",
            "headers": {"Authorization": "Bearer local-placeholder"},
        }
    ]
    assert [model.id for model in models] == [
        "bridge/custom-model",
        "gpt-5.1",
        "o4-mini",
    ]
    assert [model.name for model in models][0] == "Bridge Custom"
    assert all(model.provider == "openai" for model in models)
