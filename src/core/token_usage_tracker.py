"""Local JSONL token usage logging for OpenAI-compatible LLM calls."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from datetime import datetime, timedelta
from math import ceil
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict
from urllib.parse import urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.core.token_usage_context import token_usage_agent_display_name

logger = logging.getLogger(__name__)

UsageSource = Literal[
    "provider_usage",
    "provider_count_endpoint",
    "local_estimate",
    "missing",
]
TokenUsageStatus = Literal["success", "error", "stream_interrupted", "missing_usage"]


class TokenUsageRecord(TypedDict):
    """JSONL record for one LLM call routed through the OAuth bridge."""

    event: Literal["llm_token_usage"]
    run_id: str
    timestamp: str
    provider: str
    status: TokenUsageStatus
    query_text: str | None
    sites_scanned_or_analyzed: list[str]
    total_input_tokens: int | None
    total_output_tokens: int | None
    usage_source: UsageSource
    is_estimate: bool
    request_id: NotRequired[str | None]
    date: NotRequired[str]
    time: NotRequired[str]
    timezone: NotRequired[str]
    endpoint: NotRequired[str | None]
    agent_name: NotRequired[str | None]
    run_text: NotRequired[str | None]
    model: NotRequired[str | None]
    links_provided: NotRequired[list[str]]
    total_tokens: NotRequired[int | None]
    cached_input_tokens: NotRequired[int | None]
    reasoning_tokens: NotRequired[int | None]
    duration_ms: NotRequired[int | None]


class NormalizedUsage(TypedDict):
    """Normalized usage fields used by token usage records."""

    total_input_tokens: int | None
    total_output_tokens: int | None
    total_tokens: int | None
    cached_input_tokens: int | None
    reasoning_tokens: int | None
    usage_source: UsageSource
    is_estimate: bool


def _integer_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def missing_usage() -> NormalizedUsage:
    """Return the canonical no-usage provider shape."""
    return {
        "total_input_tokens": None,
        "total_output_tokens": None,
        "total_tokens": None,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "usage_source": "missing",
        "is_estimate": False,
    }


def estimate_text_tokens(text: str | None, model: str | None = None) -> int:
    """Estimate token count for text using the best available tokenizer."""
    if not text:
        return 0

    try:
        import tiktoken

        if model:
            try:
                encoding = tiktoken.encoding_for_model(model)
            except KeyError:
                encoding = _fallback_encoding(tiktoken)
        else:
            encoding = _fallback_encoding(tiktoken)
        return int(len(encoding.encode(text)))
    except Exception:
        return max(1, ceil(len(text) / 4))


def _fallback_encoding(tiktoken_module: Any) -> Any:
    try:
        return tiktoken_module.get_encoding("o200k_base")
    except Exception:
        return tiktoken_module.get_encoding("cl100k_base")


def estimate_usage_from_texts(
    *,
    input_text: str | None,
    output_text: str | None,
    model: str | None = None,
) -> NormalizedUsage:
    """Estimate normalized input/output token usage for local bridge runs."""
    input_tokens = estimate_text_tokens(input_text, model=model)
    output_tokens = estimate_text_tokens(output_text, model=model)
    return {
        "total_input_tokens": input_tokens,
        "total_output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "usage_source": "local_estimate",
        "is_estimate": True,
    }


def normalize_provider_usage(usage: Any) -> NormalizedUsage:
    """Normalize provider or Codex JSONL usage, rejecting fake zero totals."""
    if not isinstance(usage, dict):
        return missing_usage()

    if isinstance(usage.get("usage"), dict):
        usage = usage["usage"]

    input_tokens = _integer_or_none(
        usage.get("prompt_tokens", usage.get("input_tokens"))
    )
    output_tokens = _integer_or_none(
        usage.get("completion_tokens", usage.get("output_tokens"))
    )
    total_tokens = _integer_or_none(usage.get("total_tokens"))

    prompt_details = usage.get("prompt_tokens_details")
    input_details = usage.get("input_tokens_details")
    completion_details = usage.get("completion_tokens_details")
    output_details = usage.get("output_tokens_details")

    cached_input_tokens = _integer_or_none(
        usage.get(
            "cached_input_tokens",
            (
                prompt_details.get("cached_tokens")
                if isinstance(prompt_details, dict)
                else None
            )
            or (
                input_details.get("cached_tokens")
                if isinstance(input_details, dict)
                else None
            ),
        )
    )
    reasoning_tokens = _integer_or_none(
        usage.get(
            "reasoning_tokens",
            usage.get(
                "reasoning_output_tokens",
                (
                    completion_details.get("reasoning_tokens")
                    if isinstance(completion_details, dict)
                    else None
                )
                or (
                    output_details.get("reasoning_tokens")
                    if isinstance(output_details, dict)
                    else None
                ),
            ),
        )
    )

    if input_tokens is None or output_tokens is None:
        return missing_usage()

    if total_tokens is None:
        total_tokens = input_tokens + output_tokens

    if input_tokens == 0 and output_tokens == 0 and total_tokens == 0:
        return missing_usage()

    return {
        "total_input_tokens": input_tokens,
        "total_output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cached_input_tokens": cached_input_tokens,
        "reasoning_tokens": reasoning_tokens,
        "usage_source": "provider_usage",
        "is_estimate": False,
    }


def extract_chat_completions_usage(response_body: Any) -> NormalizedUsage:
    """Normalize OpenAI-compatible Chat Completions usage fields."""
    usage = response_body.get("usage") if isinstance(response_body, dict) else None
    if not isinstance(usage, dict):
        return missing_usage()
    return normalize_provider_usage(usage)


def extract_responses_usage(response_body: Any) -> NormalizedUsage:
    """Normalize OpenAI-compatible Responses API usage fields."""
    usage = response_body.get("usage") if isinstance(response_body, dict) else None
    if not isinstance(usage, dict):
        return missing_usage()
    return normalize_provider_usage(usage)


def timestamp_parts(timezone: str = "America/New_York") -> dict[str, str]:
    """Return ISO timestamp fields in the configured timezone."""
    try:
        tz = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        logger.warning("Unknown token usage timezone %s; falling back to UTC", timezone)
        timezone = "UTC"
        tz = ZoneInfo("UTC")
    now = datetime.now(tz)
    return {
        "timestamp": now.isoformat(timespec="milliseconds"),
        "date": now.date().isoformat(),
        "time": now.time().replace(microsecond=0).isoformat(),
        "timezone": timezone,
    }


def extract_links(text: str | None) -> list[str]:
    """Extract HTTP(S) links from user-visible query text."""
    if not text:
        return []
    return re.findall(r'https?://[^\s)\]}>"\']+', text)


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        for key in ("text", "output"):
            text = content.get(key)
            if text:
                return str(text)
        if "content" in content:
            return _content_to_text(content.get("content"))
        return ""
    if not isinstance(content, list):
        return str(content)

    parts: list[str] = []
    for item in content:
        text = _content_to_text(item)
        if text:
            parts.append(text)
    return "\n".join(parts)


def extract_user_query_from_chat_messages(messages: list[Any]) -> str | None:
    """Extract only user-visible chat message text, excluding system prompts."""
    parts: list[str] = []
    for message in messages:
        role = (
            message.get("role")
            if isinstance(message, dict)
            else getattr(message, "role", None)
        )
        if str(role).lower() != "user":
            continue
        content = (
            message.get("content")
            if isinstance(message, dict)
            else getattr(message, "content", None)
        )
        text = _content_to_text(content).strip()
        if text:
            parts.append(text)
    return "\n".join(parts) or None


def extract_user_query_from_responses_input(input_payload: Any) -> str | None:
    """Extract user-visible Responses input text, excluding instructions."""
    if isinstance(input_payload, str):
        stripped = input_payload.strip()
        return stripped or None

    parts: list[str] = []
    items = input_payload if isinstance(input_payload, list) else [input_payload]
    for item in items:
        if isinstance(item, dict):
            role = str(item.get("role") or "user").lower()
            if role != "user":
                continue
            content = item.get("content", item.get("text", item.get("output")))
        else:
            content = item
        text = _content_to_text(content).strip()
        if text:
            parts.append(text)
    return "\n".join(parts) or None


def normalize_sites_from_urls(urls: list[str]) -> list[str]:
    """Normalize URLs or labels into a sorted site list."""
    sites: set[str] = set()
    for url in urls:
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            if hostname:
                sites.add(hostname.removeprefix("www."))
                continue
        except ValueError:
            pass

        safe = url.strip()
        if safe:
            sites.add(safe)
    return sorted(sites)


def new_run_id() -> str:
    """Generate a local token-usage run identifier."""
    return f"run_{uuid4().hex}"


_TOKEN_REPORT_FILE = re.compile(r"^(\d{4}) - .+\.json$")
_WINDOWS_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_DESCRIPTION_LINE_RE = re.compile(r"(?im)^Description:\s*(.+)$")


def _integer_or_zero(value: Any) -> int:
    count = _integer_or_none(value)
    return count if count is not None else 0


def sanitize_run_text(text: str | None, *, max_length: int = 80) -> str:
    """Return user-entered text safe for Windows report filenames."""
    cleaned = " ".join((text or "").split())
    cleaned = _WINDOWS_INVALID_FILENAME_CHARS.sub("", cleaned).strip(" .")
    if not cleaned:
        return "untitled"
    return cleaned[:max_length].rstrip(" .") or "untitled"


def next_token_usage_run_id(
    description: str,
    log_dir: str | Path,
    *,
    log_file: str | Path = "token-usage.jsonl",
) -> str:
    """Create the next readable token-usage run id for a new analysis run."""
    path = Path(log_dir)
    highest = 0
    if path.exists():
        for report_file in path.glob("*.json"):
            match = _TOKEN_REPORT_FILE.match(report_file.name)
            if match:
                highest = max(highest, int(match.group(1)))
        log_path = path / log_file
        if log_path.exists():
            with log_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(record, dict):
                        continue
                    run_id = _string_or_none(record.get("run_id"))
                    if not run_id:
                        continue
                    match = _TOKEN_REPORT_FILE.match(f"{run_id}.json")
                    if match:
                        highest = max(highest, int(match.group(1)))
    return f"{highest + 1:04d} - {sanitize_run_text(description)}"


def _record_sort_key(record: dict[str, Any]) -> tuple[str, str]:
    return (
        str(record.get("timestamp") or ""),
        str(record.get("request_id") or ""),
    )


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _display_agent_name(value: Any) -> str:
    return token_usage_agent_display_name(_string_or_none(value)) or "UNKNOWN"


def _model_name(record: dict[str, Any]) -> str:
    return _string_or_none(record.get("model")) or "unknown"


def _run_text(records: list[dict[str, Any]]) -> str:
    for record in records:
        text = _string_or_none(record.get("run_text"))
        if text:
            return text
    for record in records:
        query_text = _string_or_none(record.get("query_text"))
        if not query_text:
            continue
        match = _DESCRIPTION_LINE_RE.search(query_text)
        if match:
            return match.group(1).strip()
    return "untitled"


def _report_run_id(raw_run_id: str, records: list[dict[str, Any]], index: int) -> str:
    if _TOKEN_REPORT_FILE.match(f"{raw_run_id}.json"):
        return raw_run_id
    return f"{index:04d} - {sanitize_run_text(_run_text(records))}"


def _parse_timestamp(record: dict[str, Any]) -> datetime | None:
    timestamp = _string_or_none(record.get("timestamp"))
    if timestamp:
        try:
            return datetime.fromisoformat(timestamp)
        except ValueError:
            pass

    date = _string_or_none(record.get("date"))
    time_value = _string_or_none(record.get("time"))
    if date and time_value:
        try:
            return datetime.fromisoformat(f"{date}T{time_value}")
        except ValueError:
            pass
    return None


def _time_string(value: datetime | None, fallback: Any = None) -> str | None:
    if value is not None:
        return value.time().replace(microsecond=0).isoformat()
    return _string_or_none(fallback)


def _duration_string(start: datetime | None, end: datetime | None) -> str | None:
    if start is None or end is None:
        return None
    duration = end - start
    if duration < timedelta(0):
        duration = timedelta(0)
    return str(duration).split(".", 1)[0]


def _build_agent_report(record: dict[str, Any]) -> tuple[dict[str, Any], datetime | None]:
    started_at = _parse_timestamp(record)
    duration_ms = _integer_or_none(record.get("duration_ms"))
    ended_at = (
        started_at + timedelta(milliseconds=duration_ms)
        if started_at is not None and duration_ms is not None
        else started_at
    )
    return (
        {
            "agent_name": _display_agent_name(record.get("agent_name")),
            "model": _model_name(record),
            "input_tokens": _integer_or_zero(record.get("total_input_tokens")),
            "cached_tokens": _integer_or_zero(record.get("cached_input_tokens")),
            "output_tokens": _integer_or_zero(record.get("total_output_tokens")),
            "reasoning_tokens": _integer_or_zero(record.get("reasoning_tokens")),
            "time_started": _time_string(started_at, record.get("time")),
            "time_ended": _time_string(ended_at, record.get("time")),
        },
        ended_at,
    )


def _build_model_totals(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals_by_model: dict[str, dict[str, Any]] = {}
    for record in records:
        model = _model_name(record)
        totals = totals_by_model.setdefault(
            model,
            {
                "model": model,
                "total_input_tokens": 0,
                "total_cached_tokens": 0,
                "total_output_tokens": 0,
                "total_reasoning_tokens": 0,
            },
        )
        totals["total_input_tokens"] += _integer_or_zero(
            record.get("total_input_tokens")
        )
        totals["total_cached_tokens"] += _integer_or_zero(
            record.get("cached_input_tokens")
        )
        totals["total_output_tokens"] += _integer_or_zero(
            record.get("total_output_tokens")
        )
        totals["total_reasoning_tokens"] += _integer_or_zero(
            record.get("reasoning_tokens")
        )
    return [totals_by_model[model] for model in sorted(totals_by_model)]


def _build_run_report(
    raw_run_id: str,
    records: list[dict[str, Any]],
    index: int,
) -> tuple[str, dict[str, Any]]:
    ordered_records = sorted(records, key=_record_sort_key)
    started = ordered_records[0]
    started_at = _parse_timestamp(started)
    agent_reports: list[dict[str, Any]] = []
    end_times: list[datetime] = []

    for record in ordered_records:
        agent_report, ended_at = _build_agent_report(record)
        agent_reports.append(agent_report)
        if ended_at is not None:
            end_times.append(ended_at)

    ended_at = max(end_times) if end_times else started_at
    run_id = _report_run_id(raw_run_id, ordered_records, index)
    return (
        f"{run_id}.json",
        {
            "run_id": run_id,
            "date_started": _string_or_none(started.get("date")),
            "time_started": _time_string(started_at, started.get("time")),
            "agent_calls": len(ordered_records),
            "agents": agent_reports,
            "time_ended": _time_string(ended_at, started.get("time")),
            "total_duration": _duration_string(started_at, ended_at),
            "models": _build_model_totals(ordered_records),
        },
    )


def build_token_usage_run_reports(
    records: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build readable per-run reports from raw token usage JSONL rows."""
    valid_records = sorted(
        (
            record
            for record in records
            if isinstance(record, dict) and record.get("event") == "llm_token_usage"
        ),
        key=_record_sort_key,
    )
    records_by_run: dict[str, list[dict[str, Any]]] = {}
    for record in valid_records:
        raw_run_id = _string_or_none(record.get("run_id")) or new_run_id()
        records_by_run.setdefault(raw_run_id, []).append(record)

    reports: dict[str, dict[str, Any]] = {}
    sorted_runs = sorted(
        records_by_run.items(),
        key=lambda item: _record_sort_key(sorted(item[1], key=_record_sort_key)[0]),
    )
    for index, (raw_run_id, run_records) in enumerate(sorted_runs, 1):
        filename, report = _build_run_report(raw_run_id, run_records, index)
        reports[filename] = report
    return reports


class TokenUsageTracker:
    """Append local token usage records without affecting main LLM flow."""

    def __init__(
        self,
        options: dict[str, str | Path] | None = None,
        *,
        log_dir: str | Path | None = None,
        log_file: str | Path | None = None,
        timezone: str | None = None,
    ) -> None:
        options = options or {}
        self.log_dir = Path(
            log_dir or options.get("logDir") or options.get("log_dir") or "token-usage"
        )
        self.log_file = str(
            log_file
            or options.get("logFile")
            or options.get("log_file")
            or "token-usage.jsonl"
        )
        self.timezone = str(timezone or options.get("timezone") or "America/New_York")

    @property
    def log_path(self) -> Path:
        return self.log_dir / self.log_file

    def record(self, record: TokenUsageRecord) -> None:
        """Append one JSON object per line, logging failures as warnings."""
        self.record_many([record])

    def record_many(self, records: Iterable[TokenUsageRecord]) -> None:
        """Append multiple JSON objects with a single file open."""
        try:
            enriched_records = [self._enrich_record(record) for record in records]
            if not enriched_records:
                return
            self.log_dir.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                for enriched in enriched_records:
                    handle.write(
                        json.dumps(enriched, ensure_ascii=False, sort_keys=True)
                    )
                    handle.write("\n")
        except Exception:
            logger.warning("Failed to write token usage record", exc_info=True)
            return

        self._write_run_reports()

    def _enrich_record(self, record: TokenUsageRecord) -> dict[str, Any]:
        enriched = dict(record)
        if not enriched.get("date") or not enriched.get("time"):
            enriched.update(timestamp_parts(self.timezone))
        return enriched

    def _read_jsonl_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        if not self.log_path.exists():
            return records

        with self.log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    records.append(record)
        return records

    def _write_run_reports(self) -> None:
        try:
            reports = build_token_usage_run_reports(self._read_jsonl_records())
            for filename, report in reports.items():
                report_path = self.log_dir / filename
                temp_path = report_path.with_name(f"{report_path.name}.tmp")
                with temp_path.open("w", encoding="utf-8") as handle:
                    json.dump(report, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
                temp_path.replace(report_path)
        except Exception:
            logger.warning("Failed to write token usage run report", exc_info=True)
