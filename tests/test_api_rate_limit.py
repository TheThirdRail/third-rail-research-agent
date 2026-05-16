from fastapi.testclient import TestClient
import pytest

from src.api.main import app
from src.core.exceptions import RateLimitExceededError
from src.services import analysis_service

TEST_ADMIN_KEY = "test-secret-key-for-ci"


@pytest.fixture(autouse=True)
def _configure_admin_key(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", TEST_ADMIN_KEY)
    from src.core import config as _cfg

    _cfg.get_settings.cache_clear()
    _cfg.settings = _cfg.get_settings()
    yield
    _cfg.get_settings.cache_clear()
    _cfg.settings = _cfg.get_settings()


def test_analyze_rate_limit(monkeypatch):
    def fake_analyze(self, description: str, url: str | None = None):
        raise RateLimitExceededError(
            "Gemini quota is 0 for this project; enable billing or switch provider."
        )

    monkeypatch.setattr(analysis_service.AnalysisService, "analyze", fake_analyze)

    client = TestClient(app)
    response = client.post(
        "/api/analyze",
        json={"description": "test"},
        headers={"X-Research-Agent-Key": TEST_ADMIN_KEY},
    )

    assert response.status_code == 429
    assert "Gemini quota" in response.json()["detail"]
