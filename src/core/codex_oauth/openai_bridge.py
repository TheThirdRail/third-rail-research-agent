"""OpenAI-compatible HTTP bridge backed by the local Codex CLI."""

from __future__ import annotations

import json
import time
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.core.codex_oauth import cli_adapter
from src.core.codex_oauth.safety import CodexOAuthConfigError, redact_secrets
from src.core.config import Settings


class ChatMessage(BaseModel):
    """Minimal OpenAI chat message shape accepted by the bridge."""

    role: str
    content: str | list[dict[str, Any]] | None = ""


class ChatCompletionRequest(BaseModel):
    """Subset of OpenAI chat completion fields used by LiteLLM/CrewAI."""

    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    reasoning_effort: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class ResponsesRequest(BaseModel):
    """Subset of OpenAI Responses API fields used by LiteLLM."""

    model: str
    input: Any
    stream: bool = False
    instructions: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    reasoning: dict[str, Any] | None = None
    text: dict[str, Any] | None = None
    tool_choice: Any = "auto"
    tools: list[dict[str, Any]] = Field(default_factory=list)
    top_p: float | None = None
    previous_response_id: str | None = None
    truncation: str | None = None
    user: str | None = None

    model_config = {"extra": "allow"}


def _normalize_model_id(model: str) -> str:
    """Strip LiteLLM/OpenAI provider prefixes before calling Codex CLI."""
    normalized = model.strip()
    for prefix in ("openai/", "codex/"):
        if normalized.lower().startswith(prefix):
            return normalized[len(prefix) :]
    return normalized


def _message_content_to_text(content: Any) -> str:
    """Convert supported OpenAI message content into plain text for Codex exec."""
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
            return _message_content_to_text(content.get("content"))
        return json.dumps(content, ensure_ascii=False, sort_keys=True)
    if not isinstance(content, list):
        return str(content)

    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
            continue
        if not isinstance(item, dict):
            parts.append(str(item))
            continue

        if item.get("type") in {"text", "input_text", "output_text"}:
            text = item.get("text")
            if text:
                parts.append(str(text))
        elif "content" in item:
            text = _message_content_to_text(item.get("content"))
            if text:
                parts.append(text)
        elif "output" in item:
            text = item.get("output")
            if text:
                parts.append(str(text))
    return "\n".join(parts)


def _messages_to_prompt(messages: list[ChatMessage]) -> str:
    """Flatten chat messages into a deterministic prompt for non-interactive Codex."""
    sections: list[str] = [
        "You are responding through an OpenAI-compatible local bridge.",
        "Answer the final user request using the conversation below.",
    ]
    for message in messages:
        content = _message_content_to_text(message.content).strip()
        if not content:
            continue
        sections.append(f"{message.role.title()}:\n{content}")
    return "\n\n".join(sections)


def _responses_input_to_prompt(
    input_payload: Any,
    instructions: str | None,
) -> str:
    """Flatten a Responses API input payload into a Codex exec prompt."""
    sections: list[str] = [
        "You are responding through an OpenAI-compatible local bridge.",
        "Answer the final user request using the conversation below.",
    ]
    if instructions:
        sections.append(f"System:\n{instructions.strip()}")

    if isinstance(input_payload, str):
        sections.append(f"User:\n{input_payload.strip()}")
        return "\n\n".join(section for section in sections if section.strip())

    items = input_payload if isinstance(input_payload, list) else [input_payload]
    for item in items:
        if isinstance(item, dict):
            role = str(item.get("role") or "user").title()
            content = _message_content_to_text(
                item.get("content", item.get("text", item.get("output")))
            ).strip()
        else:
            role = "User"
            content = _message_content_to_text(item).strip()
        if content:
            sections.append(f"{role}:\n{content}")

    return "\n\n".join(section for section in sections if section.strip())


def _openai_model_record(model: dict[str, Any]) -> dict[str, Any]:
    """Convert a Codex model catalog item to the OpenAI /models shape."""
    model_id = model.get("slug") or model.get("id")
    if not model_id:
        return {}
    return {
        "id": model_id,
        "object": "model",
        "created": 0,
        "owned_by": "codex",
        "name": model.get("display_name") or model_id,
    }


def _responses_payload(
    *,
    content: str,
    model: str,
    request: ResponsesRequest,
) -> dict[str, Any]:
    created = int(time.time())
    response_id = f"resp_codex_{uuid4().hex}"
    return {
        "id": response_id,
        "object": "response",
        "created_at": created,
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "instructions": request.instructions,
        "metadata": {},
        "model": model,
        "output": [
            {
                "id": f"msg_codex_{uuid4().hex}",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": content,
                        "annotations": [],
                    }
                ],
            }
        ],
        "parallel_tool_calls": False,
        "temperature": request.temperature,
        "tool_choice": request.tool_choice or "auto",
        "tools": request.tools,
        "top_p": request.top_p,
        "max_output_tokens": request.max_output_tokens,
        "previous_response_id": request.previous_response_id,
        "reasoning": request.reasoning,
        "text": request.text or {"format": None},
        "truncation": request.truncation,
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        },
        "user": request.user,
    }


def create_app(settings: Settings) -> FastAPI:
    """Create the local bridge app."""
    app = FastAPI(title="Research Agent Codex OAuth Bridge")

    @app.get("/health")
    def health() -> dict[str, Any]:
        status = cli_adapter.status(settings)
        return {
            "status": "ok" if status.exists and status.login_ok else "degraded",
            "codex_cli_exists": status.exists,
            "codex_login_ok": status.login_ok,
            "message": status.message,
        }

    @app.get("/v1/models")
    def models() -> dict[str, Any]:
        try:
            records = [
                record
                for model in cli_adapter.list_models(settings)
                if (record := _openai_model_record(model))
            ]
        except CodexOAuthConfigError as exc:
            raise HTTPException(status_code=503, detail=redact_secrets(exc)) from exc
        return {"object": "list", "data": records}

    @app.post("/v1/chat/completions")
    def chat_completions(request: ChatCompletionRequest) -> dict[str, Any]:
        if request.stream:
            raise HTTPException(
                status_code=400,
                detail="Streaming chat completions are not supported by this bridge.",
            )

        prompt = _messages_to_prompt(request.messages)
        model = _normalize_model_id(request.model)
        try:
            content = cli_adapter.run_prompt_with_model(
                prompt,
                settings,
                model=model,
                reasoning_effort=request.reasoning_effort,
            )
        except CodexOAuthConfigError as exc:
            raise HTTPException(status_code=503, detail=redact_secrets(exc)) from exc

        return {
            "id": f"chatcmpl-codex-{uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }

    @app.post("/v1/responses")
    def responses(request: ResponsesRequest) -> dict[str, Any]:
        if request.stream:
            raise HTTPException(
                status_code=400,
                detail="Streaming responses are not supported by this bridge.",
            )

        prompt = _responses_input_to_prompt(request.input, request.instructions)
        model = _normalize_model_id(request.model)
        reasoning_effort = (
            request.reasoning.get("effort") if isinstance(request.reasoning, dict) else None
        )
        try:
            content = cli_adapter.run_prompt_with_model(
                prompt,
                settings,
                model=model,
                reasoning_effort=reasoning_effort,
            )
        except CodexOAuthConfigError as exc:
            raise HTTPException(status_code=503, detail=redact_secrets(exc)) from exc

        return _responses_payload(content=content, model=model, request=request)

    return app
