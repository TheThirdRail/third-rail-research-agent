import os

os.environ["DEBUG"] = "true"

from src.core import config as core_config
from src.core.config import Settings
from src.core.llm_provider_docker import LLMRouter


def test_codex_oauth_testing_disabled_by_default(monkeypatch):
    for key in (
        "CODEX_OAUTH_TESTING_ENABLED",
        "CODEX_OAUTH_MODE",
        "CODEX_CLI_COMMAND",
        "TOKEN_USAGE_LOG_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)

    assert settings.codex_oauth_testing_enabled is False
    assert settings.codex_oauth_mode == "disabled"
    assert settings.codex_cli_command == "codex"
    assert settings.codex_require_localhost is True
    assert settings.codex_allow_public_api is False
    assert settings.codex_max_prompt_chars == 30000
    assert settings.codex_timeout_seconds == 300
    assert settings.token_usage_log_enabled is True


def test_token_usage_logging_defaults_off_in_production(monkeypatch):
    monkeypatch.delenv("TOKEN_USAGE_LOG_ENABLED", raising=False)

    settings = Settings(_env_file=None, app_env="production")

    assert settings.token_usage_log_enabled is False


def test_token_usage_logging_env_override(monkeypatch):
    monkeypatch.setenv("TOKEN_USAGE_LOG_ENABLED", "false")

    settings = Settings(_env_file=None)

    assert settings.token_usage_log_enabled is False


def test_existing_provider_config_still_loads():
    settings = Settings(
        _env_file=None,
        llm_provider="openai",
        openai_api_key="test-key",
        openai_base_url="https://api.openai.com/v1",
    )

    assert settings.llm_provider == "openai"
    assert settings.openai_api_key == "test-key"
    assert settings.openai_base_url == "https://api.openai.com/v1"


def test_debug_release_env_value_maps_to_false(monkeypatch):
    monkeypatch.setenv("DEBUG", "release")

    settings = Settings(_env_file=None)

    assert settings.debug is False


def test_codex_bridge_models_are_allowed_in_free_budget_mode(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://host.docker.internal:8787/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "local-placeholder")
    monkeypatch.setattr(core_config.settings, "codex_oauth_testing_enabled", True)
    monkeypatch.setattr(
        core_config.settings, "codex_oauth_mode", "openai_compatible_bridge"
    )
    monkeypatch.setattr(core_config.settings, "codex_require_localhost", True)
    monkeypatch.setattr(core_config.settings, "codex_allow_public_api", False)

    router = LLMRouter(provider="openai", model="gpt-5.3-codex")

    assert router._model_is_budget_free() is True
