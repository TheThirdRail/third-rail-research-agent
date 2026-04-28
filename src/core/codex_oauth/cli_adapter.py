"""Safe subprocess adapter for official Codex CLI local testing."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from src.core.codex_oauth.safety import (
    CodexOAuthConfigError,
    redact_secrets,
    validate_prompt_length,
)

CLI_MODE = "codex_cli"


@dataclass(frozen=True)
class CodexCliStatus:
    """Diagnostic status for the local Codex CLI."""

    command: str
    executable: str | None
    exists: bool
    login_ok: bool | None = None
    message: str = ""


def find_codex(command: str) -> str | None:
    """Find the official Codex CLI executable."""
    return shutil.which(command)


def _required_codex_executable(settings: Any) -> str:
    """Return the configured Codex executable or raise a safe config error."""
    command = getattr(settings, "codex_cli_command", "codex")
    executable = find_codex(command)
    if not executable:
        raise CodexOAuthConfigError(
            f"Codex CLI command not found: {command}. Run `codex login` after installing Codex CLI."
        )
    return executable


def status(settings: Any) -> CodexCliStatus:
    """Check Codex CLI availability and login status without reading token files."""
    command = getattr(settings, "codex_cli_command", "codex")
    executable = find_codex(command)
    if not executable:
        return CodexCliStatus(
            command=command,
            executable=None,
            exists=False,
            login_ok=False,
            message=f"Codex CLI command not found: {command}",
        )

    timeout = min(max(getattr(settings, "codex_timeout_seconds", 300), 1), 30)
    try:
        result = subprocess.run(
            [executable, "login", "status"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CodexCliStatus(
            command=command,
            executable=executable,
            exists=True,
            login_ok=False,
            message="Codex CLI login status timed out.",
        )
    except OSError as exc:
        return CodexCliStatus(
            command=command,
            executable=executable,
            exists=True,
            login_ok=False,
            message=redact_secrets(exc),
        )

    output = (result.stdout or result.stderr or "").strip()
    return CodexCliStatus(
        command=command,
        executable=executable,
        exists=True,
        login_ok=result.returncode == 0,
        message=redact_secrets(output),
    )


def run_prompt(prompt: str, settings: Any) -> str:
    """Run a tiny prompt through `codex exec` using stdin and shell=False."""
    return run_prompt_with_model(prompt, settings)


def run_prompt_with_model(
    prompt: str,
    settings: Any,
    *,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> str:
    """Run a prompt through `codex exec` with optional model controls."""
    validate_prompt_length(prompt, getattr(settings, "codex_max_prompt_chars", 30000))

    executable = _required_codex_executable(settings)
    timeout = getattr(settings, "codex_timeout_seconds", 300)
    args = [
        executable,
        "exec",
    ]
    if model:
        args.extend(["--model", model])
    if reasoning_effort in {"low", "medium", "high", "xhigh"}:
        args.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
    args.extend(
        [
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ephemeral",
            "--color",
            "never",
            "-",
        ]
    )

    try:
        result = subprocess.run(
            args,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CodexOAuthConfigError(
            f"Codex CLI prompt timed out after {timeout} seconds."
        ) from exc
    except OSError as exc:
        raise CodexOAuthConfigError(redact_secrets(exc)) from exc

    stdout = redact_secrets(result.stdout or "").strip()
    stderr = redact_secrets(result.stderr or "").strip()
    if result.returncode != 0:
        detail = stderr or stdout or "no output"
        raise CodexOAuthConfigError(
            f"Codex CLI prompt failed. Run `codex login` and retry. Detail: {detail}"
        )
    return stdout


def list_models(settings: Any) -> list[dict[str, Any]]:
    """Return the raw model records from `codex debug models`."""
    executable = _required_codex_executable(settings)
    timeout = min(max(getattr(settings, "codex_timeout_seconds", 300), 1), 30)

    try:
        result = subprocess.run(
            [executable, "debug", "models"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CodexOAuthConfigError("Codex CLI model discovery timed out.") from exc
    except OSError as exc:
        raise CodexOAuthConfigError(redact_secrets(exc)) from exc

    stdout = result.stdout or ""
    stderr = redact_secrets(result.stderr or "").strip()
    if result.returncode != 0:
        detail = stderr or redact_secrets(stdout).strip() or "no output"
        raise CodexOAuthConfigError(
            f"Codex CLI model discovery failed. Run `codex login` and retry. Detail: {detail}"
        )

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise CodexOAuthConfigError(
            "Codex CLI model discovery returned invalid JSON."
        ) from exc

    models = payload.get("models", [])
    if not isinstance(models, list):
        raise CodexOAuthConfigError("Codex CLI model discovery returned no model list.")
    return [model for model in models if isinstance(model, dict)]
