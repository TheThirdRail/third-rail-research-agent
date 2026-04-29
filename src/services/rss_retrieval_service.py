"""Analysis-time RSS retrieval for curated source gathering."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from src.core.config import settings
from src.tools.rss_aggregator import RSSAggregator
from src.tools.web_search import SearchResult


@dataclass
class RssRetrievalService:
    """Search curated RSS feeds before site or open-web search."""

    aggregator: RSSAggregator | None = None

    def __post_init__(self) -> None:
        if self.aggregator is None:
            self.aggregator = RSSAggregator()

    def search(
        self,
        query: str,
        *,
        domains: list[str],
        max_results: int = 8,
    ) -> list[SearchResult]:
        """Return RSS feed items matching a query and target domain list."""
        if not self.aggregator or not domains:
            return []

        target_domains = {self._normalize_domain(domain) for domain in domains}
        terms = self._query_terms(query)
        results: list[SearchResult] = []
        feed_attempts = 0
        max_feed_attempts = max(
            1,
            self._setting_int("analysis_rss_max_feeds_per_bucket", 3),
        )
        timeout_seconds = max(1, self._setting_int("analysis_rss_timeout_seconds", 6))

        for feed in self.aggregator.feeds:
            if len(results) >= max_results:
                break
            if feed_attempts >= max_feed_attempts:
                break
            feed_url = str(feed.get("url", ""))
            if not self._valid_feed_url(feed_url):
                continue
            feed_domain = self._normalize_domain(str(feed.get("url", "")))
            source_name = str(feed.get("name", "Unknown"))
            if target_domains and not self._feed_matches_targets(
                feed_domain,
                source_name,
                target_domains,
            ):
                continue
            feed_attempts += 1
            items = self.aggregator.fetch_feed(
                feed_url=feed_url,
                max_items=10,
                bias=int(feed.get("bias", 0)),
                source_name=source_name,
                timeout_seconds=timeout_seconds,
            )
            for item in items:
                if len(results) >= max_results:
                    break
                item_domain = self._normalize_domain(item.domain)
                if target_domains and item_domain and item_domain not in target_domains:
                    continue
                text = f"{item.title} {item.summary}".lower()
                if terms and not any(term in text for term in terms):
                    continue
                results.append(
                    SearchResult(
                        title=item.title,
                        url=item.url,
                        snippet=item.summary,
                        source=f"rss:{item.source_name}",
                    )
                )

        return results

    @staticmethod
    def _query_terms(query: str) -> list[str]:
        tokens = re.findall(r"[a-zA-Z0-9]{3,}", query.lower())
        stop = {"the", "and", "for", "with", "from", "this", "that", "about"}
        return [token for token in tokens if token not in stop][:8]

    @classmethod
    def _normalize_domain(cls, value: str) -> str:
        cleaned = value.lower().strip()
        cleaned = re.sub(r"^https?://", "", cleaned)
        cleaned = cleaned.split("/", 1)[0]
        if cleaned.startswith("www."):
            cleaned = cleaned[4:]
        return cleaned

    @staticmethod
    def _setting_int(name: str, default: int) -> int:
        value = getattr(settings, name, default)
        return value if isinstance(value, int) else default

    @staticmethod
    def _valid_feed_url(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @classmethod
    def _feed_matches_targets(
        cls,
        feed_domain: str,
        source_name: str,
        target_domains: set[str],
    ) -> bool:
        if feed_domain in target_domains:
            return True
        if any(feed_domain.endswith(f".{domain}") for domain in target_domains):
            return True
        normalized_name = re.sub(r"[^a-z0-9]+", "", source_name.lower())
        return any(
            re.sub(r"[^a-z0-9]+", "", domain.split(".", 1)[0]) in normalized_name
            for domain in target_domains
        )
