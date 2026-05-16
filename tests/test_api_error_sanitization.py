import logging

from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routes import analyze as analyze_routes
from src.core import config as _cfg
from src.core.exceptions import BudgetExceededError


def test_unexpected_analysis_error_returns_safe_detail(monkeypatch):
    class FakeAnalysisService:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def analyze(self, description: str, url: str | None = None, options=None):
            raise RuntimeError(
                "Traceback: provider key sk-live-secret failed inside internal stack"
            )

    monkeypatch.setattr(analyze_routes, "AnalysisService", FakeAnalysisService)
    monkeypatch.setattr(_cfg.settings, "admin_api_key", "test-admin-key")

    response = TestClient(app).post(
        "/api/analyze",
        json={"description": "test"},
        headers={"x-research-agent-key": "test-admin-key"},
    )

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail == "Analysis failed. Check server logs for details."
    assert "Traceback" not in detail
    assert "sk-live-secret" not in detail
    assert "internal stack" not in detail


def test_budget_error_preserves_402_status(monkeypatch):
    class FakeAnalysisService:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def analyze(self, description: str, url: str | None = None, options=None):
            raise BudgetExceededError("Daily budget exceeded.")

    monkeypatch.setattr(analyze_routes, "AnalysisService", FakeAnalysisService)
    monkeypatch.setattr(_cfg.settings, "admin_api_key", "test-admin-key")

    response = TestClient(app).post(
        "/api/analyze",
        json={"description": "test"},
        headers={"x-research-agent-key": "test-admin-key"},
    )

    assert response.status_code == 402
    assert response.json()["detail"] == "Daily budget exceeded."


def test_channel_upload_parse_failure_is_400_and_logs_context(monkeypatch, caplog):
    monkeypatch.setattr(_cfg.settings, "admin_api_key", "test-admin-key")
    caplog.set_level(logging.WARNING)

    response = TestClient(app).post(
        "/api/channel/upload",
        files={"file": ("profile.yaml", "channel: [broken", "text/yaml")},
        headers={"x-research-agent-key": "test-admin-key"},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Invalid file content" in detail
    assert "Traceback" not in detail
    assert "test-admin-key" not in detail
    assert "Invalid channel profile upload content" in caplog.text
    assert "profile.yaml" in caplog.text
    assert "test-admin-key" not in caplog.text


def test_channel_upload_rejects_oversized_file_before_decoding(monkeypatch):
    monkeypatch.setattr(_cfg.settings, "admin_api_key", "test-admin-key")
    monkeypatch.setattr(_cfg.settings, "max_upload_bytes", 4)

    response = TestClient(app).post(
        "/api/channel/upload",
        files={"file": ("profile.txt", b"too large", "text/plain")},
        headers={"x-research-agent-key": "test-admin-key"},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Uploaded file is too large"
