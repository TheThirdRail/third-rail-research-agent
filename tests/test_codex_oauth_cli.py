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
    assert "--json" in args
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
    assert "-c" in args
    assert 'model_reasoning_effort="high"' in args
    assert kwargs["shell"] is False


def test_cli_prompt_result_returns_content_and_provider_usage(monkeypatch):
    settings = Settings(_env_file=None, codex_cli_command="codex")

    def fake_run(args, **kwargs):
        output_path = args[args.index("--output-last-message") + 1]
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write("hello from last message")
        return SimpleNamespace(
            returncode=0,
            stdout="\n".join(
                [
                    json.dumps({"type": "thread_started"}),
                    json.dumps(
                        {
                            "type": "turn_completed",
                            "usage": {
                                "input_tokens": 12,
                                "cached_input_tokens": 3,
                                "output_tokens": 5,
                                "reasoning_output_tokens": 2,
                            },
                        }
                    ),
                ]
            ),
            stderr="",
        )

    monkeypatch.setattr(cli_adapter.shutil, "which", lambda _command: "codex")
    monkeypatch.setattr(cli_adapter.subprocess, "run", fake_run)

    result = cli_adapter.run_prompt_with_model_result("Say hello", settings)

    assert result.content == "hello from last message"
    assert result.usage == {
        "total_input_tokens": 12,
        "total_output_tokens": 5,
        "total_tokens": 17,
        "cached_input_tokens": 3,
        "reasoning_tokens": 2,
        "usage_source": "provider_usage",
        "is_estimate": False,
    }
    assert result.raw_stderr == ""


def test_cli_prompt_result_ignores_zero_json_usage(monkeypatch):
    settings = Settings(_env_file=None, codex_cli_command="codex")

    def fake_run(args, **kwargs):
        output_path = args[args.index("--output-last-message") + 1]
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write("hello")
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "type": "turn_completed",
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(cli_adapter.shutil, "which", lambda _command: "codex")
    monkeypatch.setattr(cli_adapter.subprocess, "run", fake_run)

    result = cli_adapter.run_prompt_with_model_result("Say hello", settings)

    assert result.content == "hello"
    assert result.usage is None


def test_cli_model_discovery_uses_debug_models(monkeypatch):
    settings = Settings(_env_file=None, codex_cli_command="codex")
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"models": [{"slug": "gpt-5.3-codex", "display_name": "GPT-5.3 Codex"}]}
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
