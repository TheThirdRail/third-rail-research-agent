import importlib.util
import os
from pathlib import Path

os.environ["DEBUG"] = "true"

from src.core.model_registry import ModelInfo as RegistryModelInfo

_MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "services" / "model_service.py"
_SPEC = importlib.util.spec_from_file_location("model_service_direct", _MODULE_PATH)
_MODULE = importlib.util.module_from_spec(_SPEC) if _SPEC else None
if _SPEC and _SPEC.loader and _MODULE:
    _SPEC.loader.exec_module(_MODULE)
else:
    raise RuntimeError("Failed to load model_service module for testing")

ModelService = _MODULE.ModelService


def test_openrouter_label_includes_pricing():
    model = RegistryModelInfo(
        id="m1",
        name="OpenRouter Model",
        provider="openrouter",
        input_cost_per_m=0.5,
        output_cost_per_m=1.25,
    )
    info = ModelService._to_model_info(model)

    assert "per 1M" in info.label
    assert "Free" not in info.label
    assert info.input_cost_per_m == 0.5
    assert info.output_cost_per_m == 1.25


def test_openrouter_free_label():
    model = RegistryModelInfo(
        id="m2",
        name="OpenRouter Free",
        provider="openrouter",
        input_cost_per_m=0.0,
        output_cost_per_m=0.0,
    )
    info = ModelService._to_model_info(model)

    assert info.label.endswith("Free")


def test_non_openrouter_label_has_no_free():
    model = RegistryModelInfo(
        id="m3",
        name="Gemini Model",
        provider="gemini",
        is_free=True,
    )
    info = ModelService._to_model_info(model)

    assert info.label == "Gemini Model"
    assert info.input_cost_per_m == 0.0
    assert info.output_cost_per_m == 0.0


async def test_openai_models_have_fallback_dropdown_options(monkeypatch):
    class _FakeRegistry:
        async def list_models(self, provider: str, force_refresh: bool = False):
            assert provider == "openai"
            return []

    monkeypatch.setattr(_MODULE, "get_model_registry", lambda: _FakeRegistry())

    models = await ModelService().get_models("openai")

    ids = [model.id for model in models]
    assert ids[:5] == [
        "gpt-5.3-codex",
        "gpt-5.5",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.4-nano",
    ]
    assert "gpt-4o-mini" not in ids
    assert "gpt-4o" not in ids
    assert all(model.provider == "openai" for model in models)
