from fastapi.testclient import TestClient

from src.api.main import app
from src.services import analysis_service


def test_raw_provider_rate_limit_maps_to_429(monkeypatch):
    def fake_analyze(self, description: str, url: str | None = None):
        raise Exception(
            "litellm.RateLimitError: RateLimitError: SambanovaException - Rate limit exceeded"
        )

    monkeypatch.setattr(analysis_service.AnalysisService, "analyze", fake_analyze)

    client = TestClient(app)
    response = client.post("/api/analyze", json={"description": "test"})

    assert response.status_code == 429
    detail = response.json()["detail"]
    assert "rate limit" in detail.lower()
    assert "LM Studio fallback" in detail
