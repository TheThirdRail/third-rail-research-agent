import httpx
import pytest

from src.core.model_registry import ModelRegistry


class _FakeResponse:
    def __init__(self, url: str, status_code: int, payload: dict):
        self.url = url
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", self.url)
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self) -> dict:
        return self._payload


@pytest.mark.asyncio
async def test_fetch_lmstudio_models_from_v1(monkeypatch):
    registry = ModelRegistry()

    class _Client:
        async def get(self, url: str, headers=None):  # noqa: ANN001
            return _FakeResponse(
                url,
                200,
                {"data": [{"id": "qwen2.5-7b-instruct"}, {"id": "lm_studio/phi-4"}]},
            )

    async def fake_get_client():
        return _Client()

    monkeypatch.setattr(registry, "_get_client", fake_get_client)
    monkeypatch.setattr(registry, "_lmstudio_base_url", lambda: "http://lmstudio.test")

    models = await registry._fetch_lmstudio_models()

    assert [m.id for m in models] == ["qwen2.5-7b-instruct", "phi-4"]
    assert all(m.provider == "lmstudio" for m in models)
    assert all(m.is_free for m in models)


@pytest.mark.asyncio
async def test_fetch_lmstudio_models_falls_back_to_legacy_endpoint(monkeypatch):
    registry = ModelRegistry()
    calls: list[str] = []

    class _Client:
        async def get(self, url: str, headers=None):  # noqa: ANN001
            calls.append(url)
            if url.endswith("/v1/models"):
                return _FakeResponse(url, 404, {})
            return _FakeResponse(url, 200, {"data": [{"id": "model-a"}]})

    async def fake_get_client():
        return _Client()

    monkeypatch.setattr(registry, "_get_client", fake_get_client)
    monkeypatch.setattr(registry, "_lmstudio_base_url", lambda: "http://lmstudio.test")

    models = await registry._fetch_lmstudio_models()

    assert [m.id for m in models] == ["model-a"]
    assert calls == [
        "http://lmstudio.test/v1/models",
        "http://lmstudio.test/models",
    ]


@pytest.mark.asyncio
async def test_fetch_lmstudio_models_handles_base_url_with_v1(monkeypatch):
    registry = ModelRegistry()
    calls: list[str] = []

    class _Client:
        async def get(self, url: str, headers=None):  # noqa: ANN001
            calls.append(url)
            return _FakeResponse(url, 200, {"data": [{"id": "model-b"}]})

    async def fake_get_client():
        return _Client()

    monkeypatch.setattr(registry, "_get_client", fake_get_client)
    monkeypatch.setattr(registry, "_lmstudio_base_url", lambda: "http://lmstudio.test/v1")

    models = await registry._fetch_lmstudio_models()

    assert [m.id for m in models] == ["model-b"]
    assert calls[0] == "http://lmstudio.test/v1/models"
