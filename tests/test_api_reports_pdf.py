import sys
import types

import pytest
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


def test_report_html_strips_active_content():
    html = reports.build_report_html(
        """
# Report

<script>alert("x")</script>
<p onclick="alert('x')" style="color:red">Body</p>
<iframe src="https://example.test/embed"></iframe>
<img src="https://example.test/pixel.png" onerror="alert('x')">
[safe link](https://example.test/source)
"""
    )

    assert "<script" not in html
    assert "onclick" not in html
    assert 'style="color:red"' not in html
    assert "<iframe" not in html
    assert "<img" not in html
    assert 'href="https://example.test/source"' in html
    assert "default-src 'none'; img-src data:; style-src 'unsafe-inline';" in html


def test_reports_pdf_rejects_oversized_markdown(monkeypatch):
    async def fake_render_report_pdf(markdown: str) -> bytes:
        return b"%PDF-1.4 test"

    monkeypatch.setattr(reports, "render_report_pdf", fake_render_report_pdf)
    monkeypatch.setattr(reports.settings, "max_report_markdown_chars", 4)

    response = TestClient(app).post(
        "/api/reports/pdf",
        json={"report_markdown": "too large"},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "report_markdown is too large"


@pytest.mark.asyncio
async def test_render_report_pdf_disables_javascript_and_aborts_requests(monkeypatch):
    calls: dict[str, object] = {}

    class FakeRoute:
        async def abort(self):
            calls["route_aborted"] = True

    class FakePage:
        async def set_content(self, html: str, *, wait_until: str):
            calls["html"] = html
            calls["wait_until"] = wait_until

        async def pdf(self, **kwargs):
            calls["pdf_kwargs"] = kwargs
            return b"%PDF-1.4 test"

        async def close(self):
            calls["page_closed"] = True

    class FakeContext:
        async def route(self, pattern: str, handler):
            calls["route_pattern"] = pattern
            calls["route_handler"] = handler

        async def new_page(self):
            return FakePage()

        async def close(self):
            calls["context_closed"] = True

    class FakeBrowser:
        async def new_context(self, **kwargs):
            calls["context_kwargs"] = kwargs
            return FakeContext()

        async def close(self):
            calls["browser_closed"] = True

    class FakeChromium:
        async def launch(self, **kwargs):
            calls["launch_kwargs"] = kwargs
            return FakeBrowser()

    class FakePlaywrightManager:
        async def __aenter__(self):
            return types.SimpleNamespace(chromium=FakeChromium())

        async def __aexit__(self, exc_type, exc, traceback):
            calls["playwright_closed"] = True

    fake_async_api = types.SimpleNamespace(
        async_playwright=lambda: FakePlaywrightManager()
    )
    monkeypatch.setitem(sys.modules, "playwright", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "playwright.async_api", fake_async_api)

    pdf_bytes = await reports.render_report_pdf("[source](https://example.test)")
    route_handler = calls["route_handler"]
    await route_handler(FakeRoute())

    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert calls["context_kwargs"] == {"java_script_enabled": False}
    assert calls["route_pattern"] == "**/*"
    assert calls["route_aborted"] is True
    assert calls["wait_until"] == "load"
    assert calls["page_closed"] is True
    assert calls["context_closed"] is True
    assert calls["browser_closed"] is True
