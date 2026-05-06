import json
import os
from types import SimpleNamespace

from fastapi.testclient import TestClient

os.environ["DEBUG"] = "true"

from src.core.codex_oauth import openai_bridge
from src.core.config import Settings


def _read_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_bridge_models_endpoint_returns_openai_shape(monkeypatch):
    settings = Settings(_env_file=None)
    app = openai_bridge.create_app(settings)

    monkeypatch.setattr(
        openai_bridge.cli_adapter,
        "list_models",
        lambda _settings: [
            {"slug": "gpt-5.3-codex", "display_name": "GPT-5.3 Codex"},
            {"slug": "gpt-5.5", "display_name": "GPT-5.5"},
        ],
    )

    response = TestClient(app).get("/v1/models")

    assert response.status_code == 200
    assert response.json() == {
        "object": "list",
        "data": [
            {
                "id": "gpt-5.3-codex",
                "object": "model",
                "created": 0,
                "owned_by": "codex",
                "name": "GPT-5.3 Codex",
            },
            {
                "id": "gpt-5.5",
                "object": "model",
                "created": 0,
                "owned_by": "codex",
                "name": "GPT-5.5",
            },
        ],
    }


def test_bridge_chat_completion_calls_codex_exec(monkeypatch):
    settings = Settings(_env_file=None, token_usage_log_enabled=False)
    app = openai_bridge.create_app(settings)
    captured = {}

    def fake_run_prompt(prompt, passed_settings, *, model=None, reasoning_effort=None):
        captured.update(
            {
                "prompt": prompt,
                "settings": passed_settings,
                "model": model,
                "reasoning_effort": reasoning_effort,
            }
        )
        return "bridge response"

    monkeypatch.setattr(
        openai_bridge.cli_adapter,
        "run_prompt_with_model",
        fake_run_prompt,
    )

    response = TestClient(app).post(
        "/v1/chat/completions",
        json={
            "model": "openai/gpt-5.3-codex",
            "reasoning_effort": "high",
            "messages": [
                {"role": "system", "content": "Be concise."},
                {"role": "user", "content": "Say hello."},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "gpt-5.3-codex"
    assert body["choices"][0]["message"]["content"] == "bridge response"
    assert captured["model"] == "gpt-5.3-codex"
    assert captured["reasoning_effort"] == "high"
    assert "System:\nBe concise." in captured["prompt"]
    assert "User:\nSay hello." in captured["prompt"]


def test_bridge_responses_endpoint_calls_codex_exec(monkeypatch):
    settings = Settings(_env_file=None, token_usage_log_enabled=False)
    app = openai_bridge.create_app(settings)
    captured = {}

    def fake_run_prompt(prompt, passed_settings, *, model=None, reasoning_effort=None):
        captured.update(
            {
                "prompt": prompt,
                "settings": passed_settings,
                "model": model,
                "reasoning_effort": reasoning_effort,
            }
        )
        return "responses bridge output"

    monkeypatch.setattr(
        openai_bridge.cli_adapter,
        "run_prompt_with_model",
        fake_run_prompt,
    )

    response = TestClient(app).post(
        "/v1/responses",
        json={
            "model": "openai/gpt-5.3-codex",
            "instructions": "Be concise.",
            "reasoning": {"effort": "high"},
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Say hello."}],
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "response"
    assert body["status"] == "completed"
    assert body["model"] == "gpt-5.3-codex"
    assert body["output"][0]["content"][0] == {
        "type": "output_text",
        "text": "responses bridge output",
        "annotations": [],
    }
    assert captured["model"] == "gpt-5.3-codex"
    assert captured["reasoning_effort"] == "high"
    assert "System:\nBe concise." in captured["prompt"]
    assert "User:\nSay hello." in captured["prompt"]


def test_bridge_health_reports_codex_status(monkeypatch):
    settings = Settings(_env_file=None)
    app = openai_bridge.create_app(settings)

    monkeypatch.setattr(
        openai_bridge.cli_adapter,
        "status",
        lambda _settings: SimpleNamespace(
            exists=True,
            login_ok=True,
            message="Logged in using ChatGPT",
        ),
    )

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["codex_cli_exists"] is True
    assert response.json()["codex_login_ok"] is True


def test_bridge_chat_completion_writes_missing_token_usage(monkeypatch, tmp_path):
    settings = Settings(
        _env_file=None,
        token_usage_log_enabled=True,
        token_usage_log_dir=str(tmp_path),
    )
    app = openai_bridge.create_app(settings)

    monkeypatch.setattr(
        openai_bridge.cli_adapter,
        "run_prompt_with_model",
        lambda *_args, **_kwargs: "bridge response",
    )

    response = TestClient(app).post(
        "/v1/chat/completions",
        json={
            "model": "openai/gpt-5.3-codex",
            "messages": [
                {"role": "system", "content": "Do not log this."},
                {
                    "role": "user",
                    "content": "Analyze https://example.com/article",
                },
            ],
        },
    )

    assert response.status_code == 200
    records = _read_jsonl(tmp_path / "token-usage.jsonl")
    assert len(records) == 1
    record = records[0]
    assert record["event"] == "llm_token_usage"
    assert record["endpoint"] == "/v1/chat/completions"
    assert record["model"] == "gpt-5.3-codex"
    assert record["status"] == "missing_usage"
    assert record["query_text"] == "Analyze https://example.com/article"
    assert record["links_provided"] == ["https://example.com/article"]
    assert record["sites_scanned_or_analyzed"] == ["example.com"]
    assert record["total_input_tokens"] is None
    assert record["total_output_tokens"] is None
    assert record["usage_source"] == "missing"
    assert record["is_estimate"] is False


def test_bridge_responses_writes_missing_token_usage(monkeypatch, tmp_path):
    settings = Settings(
        _env_file=None,
        token_usage_log_enabled=True,
        token_usage_log_dir=str(tmp_path),
    )
    app = openai_bridge.create_app(settings)

    monkeypatch.setattr(
        openai_bridge.cli_adapter,
        "run_prompt_with_model",
        lambda *_args, **_kwargs: "responses bridge output",
    )

    response = TestClient(app).post(
        "/v1/responses",
        json={
            "model": "openai/gpt-5.3-codex",
            "instructions": "Do not log this.",
            "metadata": {
                "sites_scanned_or_analyzed": ["https://another-site.com/report"]
            },
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Summarize https://example.com/article",
                        }
                    ],
                }
            ],
        },
    )

    assert response.status_code == 200
    records = _read_jsonl(tmp_path / "token-usage.jsonl")
    assert len(records) == 1
    record = records[0]
    assert record["endpoint"] == "/v1/responses"
    assert record["query_text"] == "Summarize https://example.com/article"
    assert record["links_provided"] == ["https://example.com/article"]
    assert record["sites_scanned_or_analyzed"] == [
        "another-site.com",
        "example.com",
    ]
    assert record["total_input_tokens"] is None
    assert record["total_output_tokens"] is None
    assert record["usage_source"] == "missing"
