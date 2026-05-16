import asyncio
import threading

import pytest

from src.api.routes import analyze as analyze_routes


@pytest.mark.asyncio
async def test_analyze_route_offloads_sync_service(monkeypatch):
    main_thread = threading.get_ident()
    observed: dict[str, int] = {}

    class FakeAnalysisService:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def analyze(self, description, url=None, options=None):
            observed["thread"] = threading.get_ident()
            with pytest.raises(RuntimeError):
                asyncio.get_running_loop()
            return {
                "story_id": "story-1",
                "report": f"report for {description}",
                "status": "completed",
                "source_count": 2,
            }

    monkeypatch.setattr(analyze_routes, "AnalysisService", FakeAnalysisService)

    response = await analyze_routes.analyze_story(
        analyze_routes.AnalyzeRequest(description="threadpool test")
    )

    assert response.story_id == "story-1"
    assert response.report == "report for threadpool test"
    assert response.status == "completed"
    assert response.source_count == 2
    assert observed["thread"] != main_thread
