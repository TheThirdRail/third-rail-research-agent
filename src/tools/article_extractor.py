"""Article Content Extraction Tool for CrewAI."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from crewai_tools import BaseTool

logger = logging.getLogger(__name__)


@dataclass
class ExtractedArticle:
    """Represents extracted article content."""

    title: str
    text: str
    author: str | None
    date: datetime | None
    domain: str
    url: str
    success: bool
    error: str | None = None


class ArticleExtractor:
    """Extracts article content from URLs using multiple methods."""

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            return parsed.netloc.replace("www.", "")
        except Exception:
            return ""

    def extract_trafilatura(self, url: str) -> ExtractedArticle:
        """Extract using trafilatura (primary method)."""
        try:
            import trafilatura

            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                return ExtractedArticle(
                    title="",
                    text="",
                    author=None,
                    date=None,
                    domain=self._extract_domain(url),
                    url=url,
                    success=False,
                    error="Failed to download page",
                )

            # Extract with metadata
            result = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                output_format="txt",
            )

            metadata = trafilatura.extract_metadata(downloaded)

            title = metadata.title if metadata else ""
            author = metadata.author if metadata else None
            date = None
            if metadata and metadata.date:
                try:
                    date = datetime.fromisoformat(metadata.date)
                except Exception:
                    pass

            return ExtractedArticle(
                title=title or "",
                text=result or "",
                author=author,
                date=date,
                domain=self._extract_domain(url),
                url=url,
                success=bool(result),
                error=None if result else "No content extracted",
            )

        except Exception as e:
            logger.warning(f"Trafilatura failed for {url}: {e}")
            return ExtractedArticle(
                title="",
                text="",
                author=None,
                date=None,
                domain=self._extract_domain(url),
                url=url,
                success=False,
                error=str(e),
            )

    def extract_newspaper(self, url: str) -> ExtractedArticle:
        """Extract using newspaper4k (fallback method)."""
        try:
            from newspaper import Article

            article = Article(url)
            article.download()
            article.parse()

            date = None
            if article.publish_date:
                if isinstance(article.publish_date, datetime):
                    date = article.publish_date
                else:
                    try:
                        date = datetime.fromisoformat(str(article.publish_date))
                    except Exception:
                        pass

            authors = article.authors
            author = authors[0] if authors else None

            return ExtractedArticle(
                title=article.title or "",
                text=article.text or "",
                author=author,
                date=date,
                domain=self._extract_domain(url),
                url=url,
                success=bool(article.text),
                error=None if article.text else "No content extracted",
            )

        except Exception as e:
            logger.warning(f"Newspaper4k failed for {url}: {e}")
            return ExtractedArticle(
                title="",
                text="",
                author=None,
                date=None,
                domain=self._extract_domain(url),
                url=url,
                success=False,
                error=str(e),
            )

    def extract(self, url: str) -> ExtractedArticle:
        """Extract article with automatic fallback."""
        # Try trafilatura first
        result = self.extract_trafilatura(url)
        if result.success and len(result.text) > 100:
            return result

        # Fallback to newspaper4k
        logger.info(f"Falling back to newspaper4k for {url}")
        return self.extract_newspaper(url)


class ArticleExtractorTool(BaseTool):
    """CrewAI tool for article content extraction."""

    name: str = "Article Extractor"
    description: str = """Extracts the full text content from a news article URL.
    Returns the article title, author, publication date, and full text.
    Use this to get the complete content of a news article for analysis."""

    def _run(self, url: str) -> str:
        """Execute article extraction.

        Args:
            url: The URL of the article to extract

        Returns:
            Formatted string with article content
        """
        extractor = ArticleExtractor()
        article = extractor.extract(url)

        if not article.success:
            return f"Failed to extract article from {url}: {article.error}"

        # Format output
        date_str = article.date.strftime("%Y-%m-%d") if article.date else "Unknown"
        author_str = article.author or "Unknown"

        output = f"""=== EXTRACTED ARTICLE ===
Title: {article.title}
Source: {article.domain}
Author: {author_str}
Date: {date_str}
URL: {article.url}

=== FULL TEXT ===
{article.text[:10000]}
"""
        # Truncate if too long
        if len(article.text) > 10000:
            output += "\n[Content truncated - showing first 10000 characters]"

        return output


class MultiArticleExtractorTool(BaseTool):
    """CrewAI tool for extracting multiple articles."""

    name: str = "Multi-Article Extractor"
    description: str = """Extracts content from multiple article URLs at once.
    Provide URLs separated by newlines or commas.
    Returns extracted content for each article."""

    def _run(self, urls: str) -> str:
        """Extract multiple articles.

        Args:
            urls: Newline or comma-separated URLs

        Returns:
            Combined extraction results
        """
        # Parse URLs
        url_list = []
        for line in urls.replace(",", "\n").split("\n"):
            url = line.strip()
            if url.startswith("http"):
                url_list.append(url)

        if not url_list:
            return "No valid URLs provided."

        extractor = ArticleExtractor()
        results = []

        for i, url in enumerate(url_list[:10], 1):  # Max 10 articles
            article = extractor.extract(url)

            if article.success:
                results.append(
                    f"--- Article {i} ---\n"
                    f"Title: {article.title}\n"
                    f"Source: {article.domain}\n"
                    f"URL: {url}\n"
                    f"Length: {len(article.text)} characters\n"
                )
            else:
                results.append(
                    f"--- Article {i} ---\n"
                    f"URL: {url}\n"
                    f"Error: {article.error}\n"
                )

        return "\n".join(results)
