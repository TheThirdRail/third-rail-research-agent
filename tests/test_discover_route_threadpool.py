import asyncio
import threading

import pytest

from src.api.routes import discover as discover_routes


@pytest.mark.asyncio
async def test_discover_route_offloads_sync_service(monkeypatch):
    main_thread = threading.get_ident()
    observed: dict[str, object] = {}

    class FakeDiscoveryService:
        def discover(self, topics=None):
            observed["thread"] = threading.get_ident()
            observed["topics"] = topics
            with pytest.raises(RuntimeError):
                asyncio.get_running_loop()
            return {
                "topics_searched": topics or ["fallback"],
                "raw_output": "discovery output",
            }

    monkeypatch.setattr(discover_routes, "DiscoveryService", FakeDiscoveryService)

    response = await discover_routes.discover_stories(
        discover_routes.DiscoverRequest(topics=["politics", "law"])
    )

    assert response.topics_searched == ["politics", "law"]
    assert response.raw_output == "discovery output"
    assert observed["topics"] == ["politics", "law"]
    assert observed["thread"] != main_thread
