"""Tests for admin API key authentication on protected routes."""

import os
from types import SimpleNamespace

# Ensure test env
os.environ.setdefault("APP_ENV", "test")

import pytest
from fastapi.testclient import TestClient

from src.core.budget_service import get_budget_service
from src.services.agent_config_service import AgentConfigService

TEST_ADMIN_KEY = "test-secret-key-for-ci"


@pytest.fixture(autouse=True)
def _set_admin_key(monkeypatch):
    """Inject a known admin key for every test in this module."""
    monkeypatch.setenv("ADMIN_API_KEY", TEST_ADMIN_KEY)
    # Force settings reload so the key takes effect
    from src.core import config as _cfg

    _cfg.get_settings.cache_clear()
    _cfg.settings = _cfg.get_settings()
    yield
    _cfg.get_settings.cache_clear()
    _cfg.settings = _cfg.get_settings()


@pytest.fixture
def client():
    from src.api.main import app

    return TestClient(app)


def _admin_headers() -> dict[str, str]:
    return {"X-Research-Agent-Key": TEST_ADMIN_KEY}


# ── Public routes remain accessible without a key ──────────────────


def test_health_no_key(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_root_no_key(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_get_config_requires_key(client):
    resp = client.get("/api/config")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized."


def test_get_budget_requires_key(client):
    resp = client.get("/api/budget")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized."


def test_channel_profile_requires_key(client):
    resp = client.get("/api/channel/profile")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized."


# ── Protected routes reject anonymous requests ─────────────────────


def test_agent_config_update_requires_key(client, monkeypatch):
    monkeypatch.setattr(
        AgentConfigService, "get_config", lambda self, name: None
    )
    resp = client.post(
        "/api/agents/profile_reader/config", json={"free_tier": True}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized."


def test_budget_limit_requires_key(client):
    resp = client.post("/api/budget/limit", json={"limit": 5.0})
    assert resp.status_code == 401


def test_budget_reset_requires_key(client):
    resp = client.post("/api/budget/reset")
    assert resp.status_code == 401


# ── Protected routes succeed with a valid key ──────────────────────


def test_agent_config_update_with_key(client, monkeypatch):
    monkeypatch.setattr(
        AgentConfigService, "get_config", lambda self, name: None
    )
    monkeypatch.setattr(
        AgentConfigService,
        "set_config",
        lambda self, **kw: SimpleNamespace(
            provider=kw.get("provider"),
            model=kw.get("model"),
            temperature=kw.get("temperature"),
            budget_limit=kw.get("budget_limit"),
            free_tier=kw.get("free_tier"),
            reasoning_effort=kw.get("reasoning_effort"),
        ),
    )
    resp = client.post(
        "/api/agents/profile_reader/config",
        json={"free_tier": True},
        headers=_admin_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["config"]["free_tier"] is True


def test_budget_reset_with_key(client, monkeypatch):
    monkeypatch.setattr(
        get_budget_service().__class__,
        "reset_daily_spend",
        lambda self: None,
    )
    resp = client.post("/api/budget/reset", headers=_admin_headers())
    assert resp.status_code == 200


def test_get_config_with_key(client):
    resp = client.get("/api/config", headers=_admin_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert "llm_provider" in body
    assert "selected_model" in body
    assert "analysis_model" in body
    assert "environment" in body


def test_get_budget_with_key(client):
    resp = client.get("/api/budget", headers=_admin_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert "current_spend" in body
    assert "limit" in body


# ── Wrong key is rejected ──────────────────────────────────────────


def test_wrong_key_rejected(client, monkeypatch):
    monkeypatch.setattr(
        AgentConfigService, "get_config", lambda self, name: None
    )
    resp = client.post(
        "/api/agents/profile_reader/config",
        json={"free_tier": True},
        headers={"X-Research-Agent-Key": "wrong-key"},
    )
    assert resp.status_code == 401


# ── No admin key configured returns 503 ────────────────────────────


def test_no_key_configured_returns_503(client, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "")
    from src.core import config as _cfg

    _cfg.get_settings.cache_clear()
    _cfg.settings = _cfg.get_settings()

    resp = client.post(
        "/api/agents/profile_reader/config",
        json={"free_tier": True},
        headers={"X-Research-Agent-Key": "anything"},
    )
    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"]


def test_protected_read_returns_503_when_admin_key_not_configured(client, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "")
    from src.core import config as _cfg

    _cfg.get_settings.cache_clear()
    _cfg.settings = _cfg.get_settings()

    resp = client.get(
        "/api/config",
        headers={"X-Research-Agent-Key": "anything"},
    )
    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"]
