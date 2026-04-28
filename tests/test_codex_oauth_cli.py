import json
import os
from types import SimpleNamespace

import pytest

os.environ["DEBUG"] = "true"

from src.core.codex_oauth import cli_adapter
from src.core.codex_oauth.safety import CodexOAuthConfigError
from src.core.config import Settings


def test_cli_mode_returns_clean_error_when_codex_missing(monkeypatch):
    settings = Settings(_env_file=None, codex_cli_command="codex-missing")
    monkeypatch.setattr(cli_adapter.shutil, "which", lambda _command: None)

    with pytest.raises(CodexOAuthConfigError) as exc:
        cli_adapter.run_prompt("hello", settings)

    assert "Codex CLI command not found" in str(exc.value)
    assert "codex login" in str(exc.value)


def test_cli_status_reports_missing_codex(monkeypatch):
    settings = Settings(_env_file=None, codex_cli_command="codex-missing")
    monkeypatch.setattr(cli_adapter.shutil, "which", lambda _command: None)

    status = cli_adapter.status(settings)

    assert status.exists is False
    assert status.login_ok is False
    assert "not found" in status.message


def test_cli_prompt_uses_stdin_and_shell_false(monkeypatch):
    settings = Settings(
        _env_file=None,
        codex_cli_command="codex",
        codex_timeout_seconds=12,
    )
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout="hello from codex", stderr="")

    monkeypatch.setattr(cli_adapter.shutil, "which", lambda _command: "codex")
    monkeypatch.setattr(cli_adapter.subprocess, "run", fake_run)

    response = cli_adapter.run_prompt("Say hello", settings)

    assert response == "hello from codex"
    args, kwargs = calls[0]
    assert args[:2] == ["codex", "exec"]
    assert args[-1] == "-"
    assert kwargs["input"] == "Say hello"
    assert kwargs["shell"] is False
    assert kwargs["timeout"] == 12


def test_cli_prompt_passes_model_and_reasoning(monkeypatch):
    settings = Settings(_env_file=None, codex_cli_command="codex")
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout="hello from codex", stderr="")

    monkeypatch.setattr(cli_adapter.shutil, "which", lambda _command: "codex")
    monkeypatch.setattr(cli_adapter.subprocess, "run", fake_run)

    response = cli_adapter.run_prompt_with_model(
        "Say hello",
        settings,
        model="gpt-5.3-codex",
        reasoning_effort="high",
    )

    assert response == "hello from codex"
    args, kwargs = calls[0]
    assert "--model" in args
    assert args[args.index("--model") + 1] == "gpt-5.3-codex"
    assert '-c' in args
    assert 'model_reasoning_effort="high"' in args
    assert kwargs["shell"] is False


def test_cli_model_discovery_uses_debug_models(monkeypatch):
    settings = Settings(_env_file=None, codex_cli_command="codex")
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "models": [
                        {"slug": "gpt-5.3-codex", "display_name": "GPT-5.3 Codex"}
                    ]
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(cli_adapter.shutil, "which", lambda _command: "codex")
    monkeypatch.setattr(cli_adapter.subprocess, "run", fake_run)

    models = cli_adapter.list_models(settings)

    assert models == [{"slug": "gpt-5.3-codex", "display_name": "GPT-5.3 Codex"}]
    args, kwargs = calls[0]
    assert args == ["codex", "debug", "models"]
    assert kwargs["shell"] is False


def test_cli_prompt_redacts_failure_output(monkeypatch):
    settings = Settings(_env_file=None, codex_cli_command="codex")

    def fake_run(args, **kwargs):
        return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="Authorization: Bearer mock-secret123456789",
        )

    monkeypatch.setattr(cli_adapter.shutil, "which", lambda _command: "codex")
    monkeypatch.setattr(cli_adapter.subprocess, "run", fake_run)

    with pytest.raises(CodexOAuthConfigError) as exc:
        cli_adapter.run_prompt("hello", settings)

    assert "mock-secret123456789" not in str(exc.value)
    assert "[REDACTED]" in str(exc.value)
