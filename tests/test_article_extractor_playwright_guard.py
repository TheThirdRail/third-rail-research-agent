import pytest

from src.tools.article_extractor import ArticleExtractor


@pytest.mark.asyncio
async def test_playwright_guard_in_event_loop():
    extractor = ArticleExtractor()
    result = extractor.extract_playwright("https://example.com")
    assert result.success is False
    assert result.error
    assert "sync API cannot run inside an asyncio event loop" in result.error
