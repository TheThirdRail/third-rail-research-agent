import sys
import types

import pytest

if "duckduckgo_search" not in sys.modules:
    sys.modules["duckduckgo_search"] = types.SimpleNamespace(DDGS=object)

import src.core.llm_provider_docker as llm
from src.core.exceptions import RateLimitExceededError
from src.core.llm_provider_docker import LLMRouter


class DummyBudget:
    def can_afford(self, model_is_free: bool = False) -> bool:
        return True

    def get_status(self) -> dict[str, float]:
        return {"current_spend": 0.0, "limit": 1.0}

    def track_spend(self, cost: float) -> None:
        return None


class DummyExc(Exception):
    pass


def _make_exc(message: str) -> Exception:
    exc = DummyExc(message)
    exc.status_code = 429
    return exc


def _make_exc_status(message: str, status_code: int) -> Exception:
    exc = DummyExc(message)
    exc.status_code = status_code
    return exc


def _setup(monkeypatch):
    monkeypatch.setattr(llm, "get_budget_service", lambda: DummyBudget())
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)


def test_gemini_quota_zero_no_retry(monkeypatch):
    _setup(monkeypatch)
    calls = {"count": 0}

    def fake_completion(*_args, **_kwargs):
        calls["count"] += 1
        raise _make_exc("RESOURCE_EXHAUSTED limit: 0")

    monkeypatch.setattr(llm, "completion", fake_completion)
    router = LLMRouter(provider="gemini", model="gemini-2.0-flash")
    router.free_tier = True

    with pytest.raises(RateLimitExceededError):
        router.complete([{"role": "user", "content": "hi"}])

    assert calls["count"] == 1


def test_gemini_rate_limit_retries(monkeypatch):
    _setup(monkeypatch)
    calls = {"count": 0}

    def fake_completion(*_args, **_kwargs):
        calls["count"] += 1
        raise _make_exc("RESOURCE_EXHAUSTED")

    monkeypatch.setattr(llm, "completion", fake_completion)
    router = LLMRouter(provider="gemini", model="gemini-2.0-flash")
    router.free_tier = True

    with pytest.raises(RateLimitExceededError):
        router.complete([{"role": "user", "content": "hi"}])

    assert calls["count"] == 6


def test_paid_mode_no_retry(monkeypatch):
    _setup(monkeypatch)
    calls = {"count": 0}

    def fake_completion(*_args, **_kwargs):
        calls["count"] += 1
        raise _make_exc("rate_limited")

    monkeypatch.setattr(llm, "completion", fake_completion)
    router = LLMRouter(provider="mistral", model="mistral-small-latest")
    router.free_tier = False

    with pytest.raises(Exception):
        router.complete([{"role": "user", "content": "hi"}])

    assert calls["count"] == 1


def test_over_capacity_retries(monkeypatch):
    _setup(monkeypatch)
    calls = {"count": 0}

    def fake_completion(*_args, **_kwargs):
        calls["count"] += 1
        raise _make_exc_status("over capacity", 503)

    monkeypatch.setattr(llm, "completion", fake_completion)
    router = LLMRouter(provider="groq", model="llama-3.3-70b-versatile")
    router.free_tier = True

    with pytest.raises(RateLimitExceededError):
        router.complete([{"role": "user", "content": "hi"}])

    assert calls["count"] == 6
