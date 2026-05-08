import asyncio

import pytest

from src.tools.article_extractor import (
    MULTI_ARTICLE_CONCURRENCY_LIMIT,
    ArticleExtractor,
    ExtractedArticle,
    MultiArticleExtractorTool,
)


@pytest.mark.asyncio
async def test_multi_article_extractor_async_uses_bounded_concurrency(monkeypatch):
    running = 0
    max_running = 0

    async def fake_extract_async(self, url: str) -> ExtractedArticle:
        nonlocal running, max_running
        running += 1
        max_running = max(max_running, running)
        await asyncio.sleep(0.01)
        running -= 1
        return ExtractedArticle(
            title=f"Title for {url}",
            text="x" * 200,
            author=None,
            date=None,
            domain="example.com",
            url=url,
            success=True,
            error=None,
            extractor_method="fake",
        )

    monkeypatch.setattr(ArticleExtractor, "extract_async", fake_extract_async)

    tool = MultiArticleExtractorTool()
    urls = "\n".join(f"https://example.com/{i}" for i in range(8))

    output = await tool._arun(urls)

    assert "--- Article 8 ---" in output
    assert 1 < max_running <= MULTI_ARTICLE_CONCURRENCY_LIMIT
