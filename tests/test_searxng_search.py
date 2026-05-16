import sys
import types

from src.core.config import settings

if "ddgs" not in sys.modules:
    sys.modules["ddgs"] = types.SimpleNamespace(DDGS=object)
if "duckduckgo_search" not in sys.modules:
    sys.modules["duckduckgo_search"] = types.SimpleNamespace(DDGS=object)

import src.tools.web_search as web_search


def test_searxng_used_for_web_search(monkeypatch):
    monkeypatch.setattr(
        settings, "searxng_base_url", "http://searxng.test", raising=False
    )
    monkeypatch.setattr(settings, "searxng_api_key", "", raising=False)
    called = {"searx": 0, "ddg": 0}

    def fake_searx_web(self, query: str, max_results: int = 10):
        called["searx"] += 1
        return [
            web_search.SearchResult(
                title="Example",
                url="https://example.com",
                snippet="snippet",
                source="searx",
            )
        ]

    def fake_ddg_web(self, query: str, max_results: int = 10):
        called["ddg"] += 1
        return []

    monkeypatch.setattr(web_search.SearxngSearch, "web_search", fake_searx_web)
    monkeypatch.setattr(web_search.DuckDuckGoSearch, "web_search", fake_ddg_web)

    tool = web_search.WebSearchTool()
    output = tool._run("test", search_type="web", max_results=1)

    assert called["searx"] == 1
    assert called["ddg"] == 0
    assert "Search results for" in output


def test_searxng_localhost_maps_to_docker_host_inside_container(monkeypatch):
    monkeypatch.setattr(
        web_search.os.path, "exists", lambda path: path == "/.dockerenv"
    )

    searcher = web_search.SearxngSearch("http://127.0.0.1:8080")

    assert searcher.base_url == "http://host.docker.internal:8080"


def test_searxng_local_urls_send_proxy_ip_headers():
    searcher = web_search.SearxngSearch("http://host.docker.internal:8080")

    assert searcher._headers()["X-Forwarded-For"] == "127.0.0.1"
    assert searcher._headers()["X-Real-IP"] == "127.0.0.1"


def test_searxng_external_urls_do_not_send_proxy_ip_headers():
    searcher = web_search.SearxngSearch("https://search.example.test")

    assert "X-Forwarded-For" not in searcher._headers()
    assert "X-Real-IP" not in searcher._headers()
