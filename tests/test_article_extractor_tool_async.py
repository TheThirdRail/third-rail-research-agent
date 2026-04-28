import inspect

import pytest

from src.tools.article_extractor import (
    ArticleExtractor,
    ArticleExtractorTool,
    ExtractedArticle,
    MultiArticleExtractorTool,
)


@pytest.mark.asyncio
async def test_article_extractor_tool_run_returns_awaitable(monkeypatch):
    tool = ArticleExtractorTool()

    async def fake_extract_async(self, url: str) -> ExtractedArticle:
        return ExtractedArticle(
            title="Example Title",
            text="Example text",
            author="Example Author",
            date=None,
            domain="example.com",
            url=url,
            success=True,
            error=None,
        )

    monkeypatch.setattr(ArticleExtractor, "extract_async", fake_extract_async)

    result = tool.run("https://example.com")
    assert inspect.isawaitable(result)

    output = await result
    assert "=== EXTRACTED ARTICLE ===" in output
    assert "Title: Example Title" in output
    assert "Source: example.com" in output
    assert "URL: https://example.com" in output


@pytest.mark.asyncio
async def test_article_extractor_tool_private_run_returns_awaitable(monkeypatch):
    tool = ArticleExtractorTool()

    async def fake_extract_async(self, url: str) -> ExtractedArticle:
        return ExtractedArticle(
            title="Example Title",
            text="Example text",
            author="Example Author",
            date=None,
            domain="example.com",
            url=url,
            success=True,
            error=None,
        )

    monkeypatch.setattr(ArticleExtractor, "extract_async", fake_extract_async)

    result = tool._run("https://example.com")
    assert inspect.isawaitable(result)

    output = await result
    assert "Title: Example Title" in output


@pytest.mark.asyncio
async def test_multi_article_extractor_tool_private_run_returns_awaitable(monkeypatch):
    tool = MultiArticleExtractorTool()

    async def fake_extract_async(self, url: str) -> ExtractedArticle:
        return ExtractedArticle(
            title=f"Title for {url}",
            text="Example text",
            author=None,
            date=None,
            domain="example.com",
            url=url,
            success=True,
            error=None,
        )

    monkeypatch.setattr(ArticleExtractor, "extract_async", fake_extract_async)

    result = tool._run("https://example.com/a\nhttps://example.com/b")
    assert inspect.isawaitable(result)

    output = await result
    assert "--- Article 1 ---" in output
    assert "--- Article 2 ---" in output
