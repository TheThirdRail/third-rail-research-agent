"""RSS News Aggregator Tool for CrewAI."""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import feedparser
import httpx
import yaml
from crewai.tools.base_tool import BaseTool

from src.core.config import settings
from src.core.time_utils import utc_now_naive
from src.utils.url_utils import extract_domain

logger = logging.getLogger(__name__)

MAX_SUMMARY_CHARS = 500
RSS_FETCH_MAX_WORKERS = 8


@dataclass
class FeedItem:
    """Represents a single RSS feed item."""

    title: str
    url: str
    domain: str
    published: datetime | None
    summary: str
    bias: int
    source_name: str


class RSSAggregator:
    """Aggregates news from multiple RSS feeds."""

    def __init__(self, feeds_config_path: str | None = None):
        """Initialize with source registry or legacy feeds config."""
        self.feeds_config_path = feeds_config_path or str(
            settings.config_dir / "rss_feeds.yaml"
        )
        self.feeds = self._load_feeds()

    def _load_feeds(self) -> list[dict[str, Any]]:
        """Load feeds from source registry, falling back to legacy config."""
        # Try source registry first
        try:
            from src.services.source_registry import get_source_registry

            registry = get_source_registry()
            grouped = registry.get_all_rss_feeds()
            feeds = []
            for category, feed_list in grouped.items():
                for feed in feed_list:
                    feed["category"] = category
                    feeds.append(feed)
            if feeds:
                logger.info("Loaded %d RSS feeds from source registry", len(feeds))
                return feeds
        except Exception as e:
            logger.warning("Source registry unavailable, using legacy config: %s", e)

        # Fallback to legacy rss_feeds.yaml
        try:
            with open(self.feeds_config_path) as f:
                config = yaml.safe_load(f)

            feeds = []
            for category, feed_list in config.get("feeds", {}).items():
                for feed in feed_list:
                    feed["category"] = category
                    feeds.append(feed)

            return feeds
        except Exception as e:
            logger.error(f"Failed to load feeds config: {e}")
            return []

    def _parse_date(self, entry: dict) -> datetime | None:
        """Parse date from feed entry."""
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            published_at = None
            try:
                published_at = datetime(*entry.published_parsed[:6])
            except (TypeError, ValueError, OverflowError):
                published_at = None
            if published_at is not None:
                return published_at
        if hasattr(entry, "updated_parsed") and entry.updated_parsed:
            updated_at = None
            try:
                updated_at = datetime(*entry.updated_parsed[:6])
            except (TypeError, ValueError, OverflowError):
                updated_at = None
            if updated_at is not None:
                return updated_at
        return None

    def fetch_feed(
        self,
        feed_url: str,
        max_items: int = 10,
        bias: int = 0,
        source_name: str = "Unknown",
        timeout_seconds: int | None = None,
    ) -> list[FeedItem]:
        """Fetch items from a single RSS feed."""
        items = []
        try:
            timeout = (
                timeout_seconds
                if timeout_seconds is not None
                else settings.analysis_rss_timeout_seconds
            )
            response = httpx.get(
                feed_url,
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": "ResearchAgent/1.0"},
            )
            response.raise_for_status()
            parsed = feedparser.parse(response.content)

            for entry in parsed.entries[:max_items]:
                title = entry.get("title", "")
                link = entry.get("link", "")
                summary = entry.get("summary", entry.get("description", ""))

                # Clean summary (remove HTML)
                if summary:
                    summary = summary[:MAX_SUMMARY_CHARS]

                items.append(
                    FeedItem(
                        title=title,
                        url=link,
                        domain=extract_domain(link),
                        published=self._parse_date(entry),
                        summary=summary,
                        bias=bias,
                        source_name=source_name,
                    )
                )

        except Exception as e:
            logger.warning(f"Failed to fetch {feed_url}: {e}")

        return items

    def fetch_all(
        self,
        max_age_hours: int = 24,
        max_per_feed: int = 5,
        categories: list[str] | None = None,
    ) -> list[FeedItem]:
        """Fetch items from all configured feeds."""
        all_items: list[FeedItem] = []
        cutoff = utc_now_naive() - timedelta(hours=max_age_hours)

        feeds = [
            feed
            for feed in self.feeds
            if not categories or feed.get("category") in categories
        ]
        if not feeds:
            return []

        def fetch_configured_feed(feed: dict[str, Any]) -> list[FeedItem]:
            return self.fetch_feed(
                feed_url=feed["url"],
                max_items=max_per_feed,
                bias=feed.get("bias", 0),
                source_name=feed.get("name", "Unknown"),
            )

        max_workers = min(RSS_FETCH_MAX_WORKERS, len(feeds))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            feed_results = executor.map(fetch_configured_feed, feeds)

            for items in feed_results:
                # Filter by age
                for item in items:
                    if item.published is None or item.published > cutoff:
                        all_items.append(item)

        return all_items

    def search_feeds(
        self,
        keywords: list[str],
        max_age_hours: int = 48,
        max_per_feed: int = 10,
        categories: list[str] | None = None,
    ) -> list[FeedItem]:
        """Search feeds for items matching keywords.

        Args:
            keywords: List of keywords to search for.
            max_age_hours: Maximum age of articles in hours.
            max_per_feed: Maximum items per feed.
            categories: Optional list of categories to filter feeds by.
                Now properly applied even when keywords are present.
        """
        all_items = self.fetch_all(
            max_age_hours=max_age_hours,
            max_per_feed=max_per_feed,
            categories=categories,
        )

        # Filter by keywords
        keywords_lower = [k.lower() for k in keywords]
        matching = []

        for item in all_items:
            text = f"{item.title} {item.summary}".lower()
            if any(kw in text for kw in keywords_lower):
                matching.append(item)

        return matching


class RSSAggregatorTool(BaseTool):
    """CrewAI tool for RSS news aggregation."""

    name: str = "RSS News Aggregator"
    description: str = """Fetches recent news articles from curated RSS feeds across
    the political spectrum. Can search by keywords or fetch all recent stories.
    Returns titles, URLs, summaries, and bias ratings."""

    def _run(
        self,
        keywords: str = "",
        max_age_hours: int = 24,
        categories: str = "",
    ) -> str:
        """Execute RSS aggregation.

        Args:
            keywords: Comma-separated keywords to search for (optional)
            max_age_hours: Maximum age of articles in hours
            categories: Comma-separated feed categories to include

        Returns:
            Formatted string of news items
        """
        aggregator = RSSAggregator()
        category_list = (
            [c.strip() for c in categories.split(",") if c.strip()]
            if categories
            else None
        )

        if keywords:
            keyword_list = [k.strip() for k in keywords.split(",")]
            # FIX: Pass categories to search_feeds (was previously ignored)
            items = aggregator.search_feeds(
                keyword_list,
                max_age_hours=max_age_hours,
                categories=category_list,
            )
        else:
            items = aggregator.fetch_all(
                max_age_hours=max_age_hours, categories=category_list
            )

        if not items:
            return "No news items found matching the criteria."

        # Format output
        output_lines = [f"Found {len(items)} news items:\n"]

        for i, item in enumerate(items[:20], 1):  # Limit to 20
            bias_label = self._bias_to_label(item.bias)
            date_str = (
                item.published.strftime("%Y-%m-%d") if item.published else "Unknown"
            )

            output_lines.append(
                f"{i}. [{bias_label}] {item.title}\n"
                f"   Source: {item.source_name} | Date: {date_str}\n"
                f"   URL: {item.url}\n"
            )

        return "\n".join(output_lines)

    def _bias_to_label(self, bias: int) -> str:
        """Convert bias score to label."""
        labels = {
            -4: "Far Left",
            -3: "Left",
            -2: "Lean Left",
            -1: "Slight Left",
            0: "Center",
            1: "Slight Right",
            2: "Lean Right",
            3: "Right",
            4: "Far Right",
        }
        return labels.get(bias, "Unknown")
