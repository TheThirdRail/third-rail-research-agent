"""Safe subprocess adapter for official Codex CLI local testing."""

from __future__ import annotations

import json
import shutil
import subprocess  # nosec B404
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.codex_oauth.safety import (
    CodexOAuthConfigError,
    redact_secrets,
    validate_prompt_length,
)
from src.core.token_usage_tracker import NormalizedUsage, normalize_provider_usage

CLI_MODE = "codex_cli"


@dataclass(frozen=True)
class CodexCliStatus:
    """Diagnostic status for the local Codex CLI."""

    command: str
    executable: str | None
    exists: bool
    login_ok: bool | None = None
    message: str = ""


@dataclass(frozen=True)
class CodexCliRunResult:
    """Structured result from `codex exec` with optional provider usage."""

    content: str
    usage: NormalizedUsage | None = None
    raw_stdout: str | None = None
    raw_stderr: str | None = None


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
        # The executable is resolved with shutil.which and args are fixed.
        result = subprocess.run(  # nosec B603
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
    return run_prompt_with_model_result(
        prompt,
        settings,
        model=model,
        reasoning_effort=reasoning_effort,
    ).content


def run_prompt_with_model_result(
    prompt: str,
    settings: Any,
    *,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> CodexCliRunResult:
    """Run a prompt through `codex exec` and parse JSONL usage when available."""
    validate_prompt_length(prompt, getattr(settings, "codex_max_prompt_chars", 30000))

    executable = _required_codex_executable(settings)
    timeout = getattr(settings, "codex_timeout_seconds", 300)
    with tempfile.TemporaryDirectory() as tmp_dir:
        last_message_path = Path(tmp_dir) / "codex-last-message.txt"
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
                "--json",
                "--output-last-message",
                str(last_message_path),
                "--color",
                "never",
                "-",
            ]
        )

        try:
            # The executable is resolved with shutil.which and args are fixed.
            result = subprocess.run(  # nosec B603
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

        content = _read_last_message(last_message_path) or _content_from_jsonl(stdout)
        if not content:
            content = stdout
        return CodexCliRunResult(
            content=content.strip(),
            usage=_usage_from_jsonl(stdout),
            raw_stdout=stdout,
            raw_stderr=stderr,
        )


def _read_last_message(path: Path) -> str:
    try:
        return redact_secrets(path.read_text(encoding="utf-8")).strip()
    except OSError:
        return ""


def _content_from_jsonl(stdout: str) -> str:
    messages: list[str] = []
    for event in _jsonl_events(stdout):
        text = _event_text(event)
        if text:
            messages.append(text)
    return "\n".join(messages).strip()


def _event_text(event: dict[str, Any]) -> str | None:
    message = event.get("message")
    if isinstance(message, str):
        return message
    item = event.get("item")
    if not isinstance(item, dict):
        return None
    details = item.get("details")
    if isinstance(details, dict):
        text = details.get("text")
        if isinstance(text, str):
            return text
    return None


def _usage_from_jsonl(stdout: str) -> NormalizedUsage | None:
    last_usage: NormalizedUsage | None = None
    for event in _jsonl_events(stdout):
        usage = event.get("usage")
        if not isinstance(usage, dict):
            continue
        normalized = normalize_provider_usage(usage)
        if normalized["usage_source"] == "provider_usage":
            last_usage = normalized
    return last_usage


def _jsonl_events(stdout: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def list_models(settings: Any) -> list[dict[str, Any]]:
    """Return the raw model records from `codex debug models`."""
    executable = _required_codex_executable(settings)
    timeout = min(max(getattr(settings, "codex_timeout_seconds", 300), 1), 30)

    try:
        # The executable is resolved with shutil.which and args are fixed.
        result = subprocess.run(  # nosec B603
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
