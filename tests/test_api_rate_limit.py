from fastapi.testclient import TestClient

from src.api.main import app
from src.core.exceptions import RateLimitExceededError
from src.services import analysis_service


def test_analyze_rate_limit(monkeypatch):
    def fake_analyze(self, description: str, url: str | None = None):
        raise RateLimitExceededError(
            "Gemini quota is 0 for this project; enable billing or switch provider."
        )

    monkeypatch.setattr(analysis_service.AnalysisService, "analyze", fake_analyze)

    client = TestClient(app)
    response = client.post("/api/analyze", json={"description": "test"})

    assert response.status_code == 429
    assert "Gemini quota" in response.json()["detail"]
