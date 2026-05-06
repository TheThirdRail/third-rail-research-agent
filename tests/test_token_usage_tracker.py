import json
import sys
from pathlib import Path

from src.core.token_usage_tracker import (
    TokenUsageTracker,
    estimate_text_tokens,
    estimate_usage_from_texts,
    extract_chat_completions_usage,
    extract_links,
    extract_responses_usage,
    extract_user_query_from_chat_messages,
    extract_user_query_from_responses_input,
    missing_usage,
    normalize_sites_from_urls,
)


def _record(query_text: str = "Analyze https://example.com/article"):
    return {
        "event": "llm_token_usage",
        "run_id": "run_test",
        "timestamp": "2026-05-06T10:30:00.000-04:00",
        "provider": "openai-oauth-bridge",
        "status": "missing_usage",
        "query_text": query_text,
        "sites_scanned_or_analyzed": ["example.com"],
        "total_input_tokens": None,
        "total_output_tokens": None,
        "usage_source": "missing",
        "is_estimate": False,
    }


def test_tracker_creates_log_dir_and_appends_jsonl(tmp_path):
    log_dir = tmp_path / "token-usage"
    tracker = TokenUsageTracker(log_dir=log_dir)

    tracker.record(_record())
    tracker.record(_record("Second query"))

    assert log_dir.exists()
    lines = (log_dir / "token-usage.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "llm_token_usage"
    assert json.loads(lines[1])["query_text"] == "Second query"


def test_chat_completions_usage_maps_provider_fields():
    usage = extract_chat_completions_usage(
        {
            "usage": {
                "prompt_tokens": 111,
                "completion_tokens": 222,
                "total_tokens": 333,
                "prompt_tokens_details": {"cached_tokens": 44},
                "completion_tokens_details": {"reasoning_tokens": 55},
            }
        }
    )

    assert usage == {
        "total_input_tokens": 111,
        "total_output_tokens": 222,
        "total_tokens": 333,
        "cached_input_tokens": 44,
        "reasoning_tokens": 55,
        "usage_source": "provider_usage",
        "is_estimate": False,
    }


def test_responses_usage_maps_provider_fields():
    usage = extract_responses_usage(
        {
            "usage": {
                "input_tokens": 111,
                "output_tokens": 222,
                "total_tokens": 333,
                "input_tokens_details": {"cached_tokens": 44},
                "output_tokens_details": {"reasoning_tokens": 55},
            }
        }
    )

    assert usage == {
        "total_input_tokens": 111,
        "total_output_tokens": 222,
        "total_tokens": 333,
        "cached_input_tokens": 44,
        "reasoning_tokens": 55,
        "usage_source": "provider_usage",
        "is_estimate": False,
    }


def test_missing_usage_has_null_totals_and_not_estimated():
    assert missing_usage() == {
        "total_input_tokens": None,
        "total_output_tokens": None,
        "total_tokens": None,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "usage_source": "missing",
        "is_estimate": False,
    }
    assert extract_chat_completions_usage({})["usage_source"] == "missing"
    assert extract_responses_usage({})["is_estimate"] is False


def test_provider_usage_requires_numeric_input_and_output_counts():
    usage = extract_chat_completions_usage({"usage": {"total_tokens": 333}})

    assert usage == missing_usage()


def test_estimate_text_tokens_counts_normal_text():
    count = estimate_text_tokens("Analyze this source for political framing.")

    assert isinstance(count, int)
    assert count > 0


def test_estimate_text_tokens_returns_zero_for_empty_text():
    assert estimate_text_tokens(None) == 0
    assert estimate_text_tokens("") == 0


def test_estimate_usage_from_texts_returns_local_estimate_shape():
    usage = estimate_usage_from_texts(
        input_text="Analyze https://example.com/article",
        output_text="Brief answer.",
        model="gpt-5.3-codex",
    )

    assert isinstance(usage["total_input_tokens"], int)
    assert usage["total_input_tokens"] > 0
    assert isinstance(usage["total_output_tokens"], int)
    assert usage["total_output_tokens"] > 0
    assert usage["total_tokens"] == (
        usage["total_input_tokens"] + usage["total_output_tokens"]
    )
    assert usage["usage_source"] == "local_estimate"
    assert usage["is_estimate"] is True


def test_estimate_text_tokens_falls_back_to_character_estimate(monkeypatch):
    monkeypatch.setitem(sys.modules, "tiktoken", None)

    assert estimate_text_tokens("123456789") == 3


def test_extract_links_from_query_text():
    links = extract_links(
        "Analyze https://example.com/article and https://another-site.com/path)."
    )

    assert links == [
        "https://example.com/article",
        "https://another-site.com/path",
    ]


def test_normalize_sites_from_urls():
    assert normalize_sites_from_urls(
        [
            "https://www.example.com/article",
            "https://another-site.com/path",
            "not a url",
        ]
    ) == ["another-site.com", "example.com", "not a url"]


def test_query_extraction_excludes_system_and_instructions():
    chat_query = extract_user_query_from_chat_messages(
        [
            {"role": "system", "content": "Never log me."},
            {"role": "user", "content": "Analyze https://example.com/article"},
        ]
    )
    responses_query = extract_user_query_from_responses_input(
        [
            {"role": "system", "content": "Never log me."},
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "User visible text"}],
            },
        ]
    )

    assert chat_query == "Analyze https://example.com/article"
    assert responses_query == "User visible text"


def test_gitignore_excludes_token_usage_folder():
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert "/token-usage/" in gitignore
