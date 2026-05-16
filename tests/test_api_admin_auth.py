"""Tests for admin API key authentication on protected routes."""

import os
from types import SimpleNamespace

# Ensure test env
os.environ.setdefault("APP_ENV", "test")

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api import dependencies as api_dependencies
from src.api.routes import analyze as analyze_routes
from src.api.routes import discover as discover_routes
from src.api.routes import reports as reports_routes
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
    monkeypatch.setattr(AgentConfigService, "get_config", lambda self, name: None)
    resp = client.post("/api/agents/profile_reader/config", json={"free_tier": True})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized."


def test_budget_limit_requires_key(client):
    resp = client.post("/api/budget/limit", json={"limit": 5.0})
    assert resp.status_code == 401


def test_budget_reset_requires_key(client):
    resp = client.post("/api/budget/reset")
    assert resp.status_code == 401


def test_analyze_requires_key(client):
    resp = client.post("/api/analyze", json={"description": "test story"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized."


def test_discover_requires_key(client):
    resp = client.post("/api/discover", json={"topics": ["politics"]})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized."


def test_reports_pdf_requires_key(client):
    resp = client.post("/api/reports/pdf", json={"report_markdown": "# Test"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized."


# ── Protected routes succeed with a valid key ──────────────────────


def test_agent_config_update_with_key(client, monkeypatch):
    monkeypatch.setattr(AgentConfigService, "get_config", lambda self, name: None)
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


def test_get_budget_with_key(client, monkeypatch):
    monkeypatch.setattr(
        get_budget_service().__class__,
        "get_status",
        lambda self: {"current_spend": 0.0, "limit": 0.0},
    )
    resp = client.get("/api/budget", headers=_admin_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert "current_spend" in body
    assert "limit" in body


def test_analyze_with_key(client, monkeypatch):
    class FakeAnalysisService:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def analyze(self, description, url=None, options=None):
            return {
                "story_id": "story-1",
                "report": f"report for {description}",
                "status": "completed",
                "source_count": 1,
            }

    monkeypatch.setattr(analyze_routes, "AnalysisService", FakeAnalysisService)

    resp = client.post(
        "/api/analyze",
        json={"description": "test story"},
        headers=_admin_headers(),
    )

    assert resp.status_code == 200
    assert resp.json()["story_id"] == "story-1"


def test_discover_with_key(client, monkeypatch):
    class FakeDiscoveryService:
        def discover(self, topics=None):
            return {
                "topics_searched": topics or ["fallback"],
                "raw_output": "discovery output",
            }

    monkeypatch.setattr(discover_routes, "DiscoveryService", FakeDiscoveryService)

    resp = client.post(
        "/api/discover",
        json={"topics": ["politics"]},
        headers=_admin_headers(),
    )

    assert resp.status_code == 200
    assert resp.json()["topics_searched"] == ["politics"]


def test_reports_pdf_with_key(client, monkeypatch):
    async def fake_render_report_pdf(markdown: str) -> bytes:
        return b"%PDF-1.4 test"

    monkeypatch.setattr(reports_routes, "render_report_pdf", fake_render_report_pdf)

    resp = client.post(
        "/api/reports/pdf",
        json={"report_markdown": "# Test"},
        headers=_admin_headers(),
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


@pytest.mark.asyncio
async def test_expensive_endpoint_limiter_returns_429_when_saturated(monkeypatch):
    from src.core import config as _cfg

    monkeypatch.setattr(_cfg.settings, "expensive_endpoint_concurrency_limit", 1)
    semaphore = api_dependencies._get_expensive_endpoint_semaphore()
    assert semaphore.acquire(blocking=False)
    try:
        dependency = api_dependencies.require_expensive_endpoint_slot()
        with pytest.raises(HTTPException) as exc_info:
            await anext(dependency)
        assert exc_info.value.status_code == 429
        assert exc_info.value.detail == "Expensive endpoint concurrency limit exceeded."
    finally:
        semaphore.release()


# ── Wrong key is rejected ──────────────────────────────────────────


def test_wrong_key_rejected(client, monkeypatch):
    monkeypatch.setattr(AgentConfigService, "get_config", lambda self, name: None)
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
