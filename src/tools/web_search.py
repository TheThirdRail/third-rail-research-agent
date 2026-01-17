"""DuckDuckGo Web Search Tool for CrewAI."""

import logging
import time
from dataclasses import dataclass
from typing import Any

from crewai_tools import BaseTool
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Represents a single search result."""

    title: str
    url: str
    snippet: str
    source: str


class DuckDuckGoSearch:
    """Wrapper for DuckDuckGo search API."""

    def __init__(self, timeout: int = 10):
        """Initialize search client."""
        self.timeout = timeout
        self._last_request = 0
        self._min_delay = 1.0  # Minimum seconds between requests

    def _rate_limit(self) -> None:
        """Implement polite rate limiting."""
        elapsed = time.time() - self._last_request
        if elapsed < self._min_delay:
            time.sleep(self._min_delay - elapsed)
        self._last_request = time.time()

    def news_search(
        self,
        query: str,
        max_results: int = 10,
        time_range: str = "w",  # d=day, w=week, m=month
    ) -> list[SearchResult]:
        """Search DuckDuckGo News."""
        self._rate_limit()
        results = []

        try:
            with DDGS() as ddgs:
                for r in ddgs.news(
                    query,
                    max_results=max_results,
                    timelimit=time_range,
                ):
                    results.append(
                        SearchResult(
                            title=r.get("title", ""),
                            url=r.get("url", ""),
                            snippet=r.get("body", ""),
                            source=r.get("source", ""),
                        )
                    )
        except Exception as e:
            logger.error(f"News search failed: {e}")

        return results

    def web_search(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[SearchResult]:
        """Search DuckDuckGo Web."""
        self._rate_limit()
        results = []

        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append(
                        SearchResult(
                            title=r.get("title", ""),
                            url=r.get("href", ""),
                            snippet=r.get("body", ""),
                            source=r.get("source", ""),
                        )
                    )
        except Exception as e:
            logger.error(f"Web search failed: {e}")

        return results


class WebSearchTool(BaseTool):
    """CrewAI tool for DuckDuckGo web search."""

    name: str = "Web Search"
    description: str = """Searches the web using DuckDuckGo. Can search for news
    articles or general web pages. Returns titles, URLs, and snippets.
    Use this to find additional sources or verify information."""

    def _run(
        self,
        query: str,
        search_type: str = "news",
        max_results: int = 10,
        time_range: str = "w",
    ) -> str:
        """Execute web search.

        Args:
            query: Search query string
            search_type: 'news' for news articles, 'web' for general
            max_results: Maximum results to return (1-20)
            time_range: Time range for news (d=day, w=week, m=month)

        Returns:
            Formatted string of search results
        """
        searcher = DuckDuckGoSearch()
        max_results = min(max(1, max_results), 20)  # Clamp to 1-20

        if search_type == "news":
            results = searcher.news_search(query, max_results, time_range)
        else:
            results = searcher.web_search(query, max_results)

        if not results:
            return f"No results found for query: {query}"

        # Format output
        output_lines = [f"Search results for '{query}' ({len(results)} found):\n"]

        for i, result in enumerate(results, 1):
            output_lines.append(
                f"{i}. {result.title}\n"
                f"   Source: {result.source}\n"
                f"   URL: {result.url}\n"
                f"   {result.snippet[:200]}...\n"
            )

        return "\n".join(output_lines)


class NewsSearchTool(BaseTool):
    """Specialized news search tool for CrewAI."""

    name: str = "News Search"
    description: str = """Searches DuckDuckGo News for recent articles on a topic.
    Best for finding current news coverage of events and stories.
    Returns article titles, sources, URLs, and summaries."""

    def _run(
        self,
        query: str,
        max_results: int = 10,
        time_range: str = "w",
    ) -> str:
        """Execute news search.

        Args:
            query: Search query string
            max_results: Maximum results (1-20)
            time_range: d=past day, w=past week, m=past month

        Returns:
            Formatted string of news results
        """
        searcher = DuckDuckGoSearch()
        results = searcher.news_search(query, min(max(1, max_results), 20), time_range)

        if not results:
            return f"No news found for: {query}"

        output_lines = [f"News results for '{query}':\n"]

        for i, result in enumerate(results, 1):
            output_lines.append(
                f"{i}. {result.title}\n"
                f"   Source: {result.source} | URL: {result.url}\n"
            )

        return "\n".join(output_lines)
