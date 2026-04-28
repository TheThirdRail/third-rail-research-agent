from src.agents import config as agents_config


def test_lmstudio_fallback_chain_present_for_non_lmstudio_primary(monkeypatch):
    monkeypatch.setattr(
        agents_config.settings,
        "lmstudio_fallback_enabled",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        agents_config.settings,
        "lmstudio_fallback_model",
        "lm_studio/qwen2.5-7b-instruct",
        raising=False,
    )

    fallbacks = agents_config._build_lmstudio_fallbacks("sambanova")

    assert fallbacks == ["lm_studio/qwen2.5-7b-instruct"]


def test_lmstudio_fallback_chain_skipped_for_native_crewai_provider(monkeypatch):
    monkeypatch.setattr(
        agents_config.settings,
        "lmstudio_fallback_enabled",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        agents_config.settings,
        "lmstudio_fallback_model",
        "qwen2.5-7b-instruct",
        raising=False,
    )

    fallbacks = agents_config._build_lmstudio_fallbacks("openai")

    assert fallbacks == []


def test_lmstudio_fallback_chain_disabled(monkeypatch):
    monkeypatch.setattr(
        agents_config.settings,
        "lmstudio_fallback_enabled",
        False,
        raising=False,
    )
    monkeypatch.setattr(
        agents_config.settings,
        "lmstudio_fallback_model",
        "qwen2.5-7b-instruct",
        raising=False,
    )

    fallbacks = agents_config._build_lmstudio_fallbacks("sambanova")

    assert fallbacks == []
