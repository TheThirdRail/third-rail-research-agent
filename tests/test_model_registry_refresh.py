import pytest

from src.core.model_registry import ModelInfo, ModelRegistry


@pytest.mark.asyncio
async def test_model_registry_force_refresh():
    registry = ModelRegistry()
    calls = {"count": 0}

    async def fake_fetch(provider: str):
        calls["count"] += 1
        return [ModelInfo(id="m1", name="m1", provider=provider)]

    registry._fetch_models_impl = fake_fetch  # type: ignore[method-assign]

    await registry.list_models("openrouter")
    await registry.list_models("openrouter")
    await registry.list_models("openrouter", force_refresh=True)

    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_model_registry_close_is_idempotent_and_clears_client():
    registry = ModelRegistry()

    class FakeClient:
        def __init__(self):
            self.close_count = 0

        async def aclose(self):
            self.close_count += 1

    client = FakeClient()
    registry._client = client

    await registry.close()
    await registry.close()

    assert client.close_count == 1
    assert registry._client is None
