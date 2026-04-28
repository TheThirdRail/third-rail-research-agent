"""Service layer for story discovery.

Encapsulates the discovery workflow, providing a clean interface
for CLI and API consumers.
"""

import logging
from typing import Any

from src.core.config import settings
from src.crews import run_discovery
from src.tools.article_extractor import ArticleExtractor
from src.tools.channel_profile_loader import channel_loader
from src.tools.rss_aggregator import FeedItem, RSSAggregator
from src.tools.web_search import _get_searcher

logger = logging.getLogger(__name__)


class DiscoveryService:
    """Service for orchestrating story discovery workflows.

    Wraps the CrewAI discovery workflow with channel profile
    integration and consistent interface.
    """

    def __init__(self) -> None:
        """Initialize discovery service."""
        pass

    def _load_channel_topics(self) -> list[str]:
        """Load topics from channel profile.

        Returns:
            List of topic keywords from profile, or defaults.
        """
        try:
            scope = channel_loader.load(settings.channel_profile_path)
            return scope.topics[:20]
        except FileNotFoundError:
            logger.warning("No channel profile found, using defaults")
            return ["politics", "geopolitics", "news"]
        except Exception as exc:
            logger.warning("Error loading channel profile: %s", exc)
            return ["politics", "geopolitics", "news"]

    def _normalize_url(self, url: str) -> str:
        if not url:
            return ""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            path = parsed.path.rstrip("/")
            return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"
        except Exception:
            return url.lower().rstrip("/")

    def _build_queries(self, topics: list[str]) -> list[str]:
        queries: list[str] = []
        trimmed = [t.strip() for t in topics if t.strip()]
        if not trimmed:
            return ["breaking news politics"]

        queries.append(" ".join(trimmed[:3]))
        queries.extend(trimmed[:5])

        seen: set[str] = set()
        deduped: list[str] = []
        for query in queries:
            key = query.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(query)
        return deduped[:6]

    def _format_rss_item(self, item: FeedItem) -> dict[str, str]:
        published = item.published.isoformat() if item.published else ""
        return {
            "title": item.title,
            "url": item.url,
            "domain": item.domain,
            "summary": item.summary or "",
            "source": item.source_name,
            "method": "rss",
            "published": published,
        }

    def _prefetch_discovery_context(self, topics: list[str], count: int) -> str:
        """Build deterministic prefetch context using RSS + search enrichment."""
        target = max(1, count)
        enrichment_threshold = max(1, int(target * 0.6))

        records: list[dict[str, str]] = []
        seen_urls: set[str] = set()

        rss = RSSAggregator()
        rss_items = rss.search_feeds(topics[:8], max_age_hours=48, max_per_feed=10)

        for item in rss_items:
            normalized = self._normalize_url(item.url)
            if not normalized or normalized in seen_urls:
                continue
            seen_urls.add(normalized)
            records.append(self._format_rss_item(item))
            if len(records) >= target:
                break

        if len(records) < enrichment_threshold:
            logger.info(
                "RSS coverage sparse (%s/%s); enriching with search and extraction",
                len(records),
                enrichment_threshold,
            )
            searcher = _get_searcher()
            extractor = ArticleExtractor()

            for query in self._build_queries(topics):
                if len(records) >= target:
                    break
                try:
                    results = searcher.news_search(query, max_results=10, time_range="w")
                except Exception as exc:
                    logger.warning("Discovery search failed for '%s': %s", query, exc)
                    continue

                for result in results:
                    if len(records) >= target:
                        break
                    normalized = self._normalize_url(result.url)
                    if not normalized or normalized in seen_urls:
                        continue
                    if not result.url.startswith("http"):
                        continue

                    seen_urls.add(normalized)
                    article = extractor.extract(result.url)

                    if article.success and len(article.text) >= 200:
                        records.append(
                            {
                                "title": article.title or result.title,
                                "url": result.url,
                                "domain": article.domain,
                                "summary": article.text[:1200],
                                "source": result.source,
                                "method": article.extractor_method or "search_extract",
                                "published": (
                                    article.date.isoformat() if article.date else ""
                                ),
                            }
                        )
                    else:
                        records.append(
                            {
                                "title": result.title,
                                "url": result.url,
                                "domain": self._normalize_url(result.url).split("/")[2],
                                "summary": result.snippet[:800],
                                "source": result.source,
                                "method": "search_snippet",
                                "published": "",
                            }
                        )

        lines = ["DETERMINISTIC PREFETCHED DISCOVERY INPUTS (Prioritize these):"]
        for idx, record in enumerate(records[: target * 2], 1):
            lines.extend(
                [
                    f"{idx}. {record['title']}",
                    f"   URL: {record['url']}",
                    f"   Domain: {record['domain']}",
                    f"   Source: {record['source']}",
                    f"   Method: {record['method']}",
                    f"   Published: {record['published'] or 'unknown'}",
                    f"   Summary: {record['summary'][:500]}",
                ]
            )

        return "\n".join(lines)

    def discover(
        self,
        topics: list[str] | None = None,
        count: int = 10,
    ) -> dict[str, Any]:
        """Run discovery workflow to find relevant stories.

        Args:
            topics: Optional list of topic keywords. If not provided,
                loads from channel profile.

        Returns:
            Dictionary with topics_searched and raw_output.
        """
        topic_list = topics if topics else self._load_channel_topics()

        logger.info("Discovering stories for topics: %s...", topic_list[:5])

        prefetched_context = None
        if settings.discovery_enrichment_enabled:
            prefetched_context = self._prefetch_discovery_context(topic_list, count)

        result = run_discovery(
            topic_list,
            count=count,
            prefetched_context=prefetched_context,
        )

        logger.info("Discovery complete")

        return {
            "topics_searched": result.get("topics_searched", topic_list),
            "raw_output": result.get("raw_output", ""),
        }
