from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routes import analyze as analyze_routes
from src.core import config as _cfg
from src.core.exceptions import RateLimitExceededError

TEST_ADMIN_KEY = "test-secret-key-for-ci"


def test_analyze_rate_limit(monkeypatch):
    class FakeAnalysisService:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def analyze(self, description: str, url: str | None = None):
            raise RateLimitExceededError(
                "Gemini quota is 0 for this project; enable billing or switch provider."
            )

    monkeypatch.setattr(analyze_routes, "AnalysisService", FakeAnalysisService)
    monkeypatch.setattr(_cfg.settings, "admin_api_key", TEST_ADMIN_KEY)

    client = TestClient(app)
    response = client.post(
        "/api/analyze",
        json={"description": "test"},
        headers={"x-research-agent-key": TEST_ADMIN_KEY},
    )

    assert response.status_code == 429
    assert "Gemini quota" in response.json()["detail"]
