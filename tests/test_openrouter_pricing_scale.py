import pytest

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

    async def get(self, *_args, **_kwargs):
        return DummyResponse(self._payload)


@pytest.mark.asyncio
async def test_openrouter_pricing_scaled_to_per_million():
    registry = ModelRegistry()
    payload = {
        "data": [
            {
                "id": "model-1",
                "name": "Model 1",
                "pricing": {"prompt": "0.0000002", "completion": "0.0000004"},
            }
        ]
    }
    dummy = DummyClient(payload)

    async def fake_get_client():
        return dummy

    registry._get_client = fake_get_client  # type: ignore[method-assign]

    models = await registry._fetch_openrouter_models()

    assert len(models) == 1
    assert models[0].input_cost_per_m == pytest.approx(0.2)
    assert models[0].output_cost_per_m == pytest.approx(0.4)
