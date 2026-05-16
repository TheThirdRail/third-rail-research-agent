"""Web Search Tool for CrewAI (SearxNG primary, DuckDuckGo fallback)."""

import logging
import os
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from crewai.tools.base_tool import BaseTool

from src.core.config import settings

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
        try:
            from ddgs import DDGS
        except Exception:
            try:
                from duckduckgo_search import DDGS
            except Exception as e:
                raise ImportError(
                    "ddgs is not installed. Install it or configure SEARXNG_BASE_URL."
                ) from e
        self._ddgs_cls = DDGS
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
            with self._ddgs_cls() as ddgs:
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
        except Exception:
            logger.warning(
                "Search backend failed: backend=duckduckgo type=news query=%r max_results=%d time_range=%s",
                _safe_query(query),
                max_results,
                time_range,
                exc_info=True,
            )

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
            with self._ddgs_cls() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append(
                        SearchResult(
                            title=r.get("title", ""),
                            url=r.get("href", ""),
                            snippet=r.get("body", ""),
                            source=r.get("source", ""),
                        )
                    )
        except Exception:
            logger.warning(
                "Search backend failed: backend=duckduckgo type=web query=%r max_results=%d",
                _safe_query(query),
                max_results,
                exc_info=True,
            )

        return results


class SearxngSearch:
    """Wrapper for SearxNG search API."""

    _LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "host.docker.internal", "searxng"}

    def __init__(self, base_url: str, api_key: str | None = None, timeout: int = 10):
        self.base_url = _docker_safe_searxng_base_url(base_url).rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._last_request = 0
        self._min_delay = 0.5

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < self._min_delay:
            time.sleep(self._min_delay - elapsed)
        self._last_request = time.time()

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if self._is_local_base_url():
            # Local SearXNG logs bot-detection errors without proxy IP headers.
            headers["X-Forwarded-For"] = "127.0.0.1"
            headers["X-Real-IP"] = "127.0.0.1"
        return headers

    def _is_local_base_url(self) -> bool:
        try:
            host = urlparse(self.base_url).hostname or ""
        except Exception:
            return False
        return host.lower() in self._LOCAL_HOSTS

    def _request(self, params: dict[str, str]) -> list[SearchResult]:
        self._rate_limit()
        results: list[SearchResult] = []

        try:
            response = httpx.get(
                f"{self.base_url}/search",
                params=params,
                headers=self._headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            for item in data.get("results", []):
                url = item.get("url", "")
                snippet = item.get("content", "") or item.get("snippet", "")
                source = item.get("engine", "") or item.get("source", "")
                if not source:
                    try:
                        source = urlparse(url).netloc
                    except Exception:
                        source = ""
                results.append(
                    SearchResult(
                        title=item.get("title", ""),
                        url=url,
                        snippet=snippet,
                        source=source,
                    )
                )
        except Exception:
            logger.warning(
                "Search backend failed: backend=searxng query=%r categories=%s",
                _safe_query(params.get("q", "")),
                params.get("categories", "general"),
                exc_info=True,
            )

        return results

    def news_search(self, query: str, max_results: int = 10, time_range: str = "w"):
        time_map = {"d": "day", "w": "week", "m": "month"}
        params = {
            "q": query,
            "format": "json",
            "categories": "news",
            "time_range": time_map.get(time_range, "week"),
            "language": "en",
            "safesearch": "0",
        }
        results = self._request(params)
        return results[:max_results]

    def web_search(self, query: str, max_results: int = 10):
        params = {
            "q": query,
            "format": "json",
            "language": "en",
            "safesearch": "0",
        }
        results = self._request(params)
        return results[:max_results]


class WebSearchTool(BaseTool):
    """CrewAI tool for web search."""

    name: str = "Web Search"
    description: str = """Searches the web using SearxNG (if configured) with
    DuckDuckGo as a fallback. Can search for news articles or general web pages.
    Returns titles, URLs, and snippets. Use this to find additional sources
    or verify information."""

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
        searcher = _get_searcher()
        max_results = min(max(1, max_results), 20)  # Clamp to 1-20

        if search_type == "news":
            results = searcher.news_search(query, max_results, time_range)
        else:
            results = searcher.web_search(query, max_results)

        if not results:
            if settings.searxng_base_url:
                return (
                    f"No results found for query: {query} (SearxNG configured; "
                    "DuckDuckGo fallback disabled)"
                )
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
    description: str = """Searches SearxNG News (if configured) with DuckDuckGo News
    as a fallback. Best for finding current news coverage of events and stories.
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
        searcher = _get_searcher()
        results = searcher.news_search(query, min(max(1, max_results), 20), time_range)

        if not results:
            if settings.searxng_base_url:
                return (
                    f"No news found for: {query} (SearxNG configured; "
                    "DuckDuckGo fallback disabled)"
                )
            return f"No news found for: {query}"

        output_lines = [f"News results for '{query}':\n"]

        for i, result in enumerate(results, 1):
            output_lines.append(
                f"{i}. {result.title}\n   Source: {result.source} | URL: {result.url}\n"
            )

        return "\n".join(output_lines)


def _get_searcher() -> SearxngSearch | DuckDuckGoSearch:
    """Select the search backend. If SearxNG is configured, use it only."""
    if settings.searxng_base_url:
        base_url = settings.searxng_base_url.strip()
        if not base_url.startswith(("http://", "https://")):
            raise ValueError(
                "SEARXNG_BASE_URL must include http:// or https:// (DuckDuckGo fallback disabled)."
            )
        return SearxngSearch(base_url, settings.searxng_api_key or None)
    return DuckDuckGoSearch()


def _docker_safe_searxng_base_url(base_url: str) -> str:
    """Map host-loopback SearxNG URLs to the Docker host from inside containers."""
    try:
        parsed = urlparse(base_url)
        if os.path.exists("/.dockerenv") and parsed.hostname in {
            "localhost",
            "127.0.0.1",
            "0.0.0.0",  # nosec B104
            "::1",
        }:
            netloc = "host.docker.internal"
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            return parsed._replace(netloc=netloc).geturl()
    except Exception:
        return base_url

    return base_url


def _safe_query(query: str, max_chars: int = 160) -> str:
    """Return bounded query context for logs without request headers or keys."""
    compacted = " ".join(str(query).split())
    if len(compacted) <= max_chars:
        return compacted
    return compacted[:max_chars].rstrip() + "..."
