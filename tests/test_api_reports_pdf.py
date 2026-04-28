import sys
import types

from fastapi.testclient import TestClient

if "duckduckgo_search" not in sys.modules:
    sys.modules["duckduckgo_search"] = types.SimpleNamespace(DDGS=object)

from src.api.main import app
from src.api.routes import reports


def test_reports_pdf_endpoint(monkeypatch):
    async def fake_render_report_pdf(markdown: str) -> bytes:
        return b"%PDF-1.4 test"

    monkeypatch.setattr(reports, "render_report_pdf", fake_render_report_pdf)

    client = TestClient(app)
    response = client.post("/api/reports/pdf", json={"report_markdown": "# Test"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-1.4")
