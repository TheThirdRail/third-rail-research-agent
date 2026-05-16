"""RSS metadata fallback resolver for blocked seed URLs."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from src.tools.rss_aggregator import FeedItem, RSSAggregator
from src.utils.url_utils import extract_domain


@dataclass
class RssFallbackResult:
    """Resolved RSS metadata for a URL."""

    title: str
    url: str
    summary: str
    published: datetime | None
    source_name: str
    domain: str
    match_confidence: float
    match_type: str


class RssFallbackService:
    """Resolves source metadata from RSS feeds when page extraction is blocked."""

    _DOMAIN_HINTS: dict[str, tuple[str, ...]] = {
        "nytimes.com": ("new york times", "nyt", "rss.nytimes.com"),
        "washingtonpost.com": ("washington post", "feeds.washingtonpost.com"),
        "cnn.com": ("cnn", "rss.cnn.com"),
        "foxnews.com": ("fox news", "foxnews"),
        "wsj.com": ("wall street journal", "a.dj.com"),
    }

    def __init__(self, feeds_config_path: str | None = None) -> None:
        self._aggregator = RSSAggregator(feeds_config_path)

    def _normalize_url(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            path = parsed.path.rstrip("/")
            return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"
        except Exception:
            return url.lower().rstrip("/")

    def _clean_summary(self, value: str) -> str:
        text = re.sub(r"<[^>]+>", " ", value or "")
        text = html.unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    def _tokenize(self, value: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9]{3,}", value.lower())
            if token not in {"the", "and", "for", "with", "from", "that", "this"}
        }

    def _iter_feed_items(
        self, feeds: list[dict[str, Any]], max_items: int = 80
    ) -> list[FeedItem]:
        items: list[FeedItem] = []
        for feed in feeds:
            items.extend(
                self._aggregator.fetch_feed(
                    feed_url=feed["url"],
                    max_items=max_items,
                    bias=feed.get("bias", 0),
                    source_name=feed.get("name", "Unknown"),
                )
            )
        return items

    def get_candidate_feeds_for_domain(self, domain: str) -> list[dict[str, Any]]:
        """Return candidate feeds for a news domain."""
        domain = (domain or "").replace("www.", "").lower()
        if not domain:
            return self._aggregator.feeds

        hints = self._DOMAIN_HINTS.get(domain, ())
        selected: list[dict[str, Any]] = []

        for feed in self._aggregator.feeds:
            feed_url = feed.get("url", "")
            feed_host = extract_domain(feed_url)
            feed_name = (feed.get("name", "") or "").lower()

            if domain in feed_host or feed_host in domain:
                selected.append(feed)
                continue

            if any(hint in feed_name or hint in feed_url.lower() for hint in hints):
                selected.append(feed)

        return selected or self._aggregator.feeds

    def _to_result(
        self,
        item: FeedItem,
        confidence: float,
        match_type: str,
    ) -> RssFallbackResult:
        return RssFallbackResult(
            title=item.title,
            url=item.url,
            summary=self._clean_summary(item.summary),
            published=item.published,
            source_name=item.source_name,
            domain=item.domain,
            match_confidence=confidence,
            match_type=match_type,
        )

    def resolve_by_url(self, url: str) -> RssFallbackResult | None:
        """Resolve exact URL match from RSS feeds."""
        normalized_target = self._normalize_url(url)
        domain = extract_domain(url)
        feeds = self.get_candidate_feeds_for_domain(domain)

        for item in self._iter_feed_items(feeds):
            if self._normalize_url(item.url) == normalized_target:
                return self._to_result(item, confidence=1.0, match_type="exact_url")

        return None

    def resolve_by_slug(
        self,
        url: str,
        title_hint: str | None = None,
    ) -> RssFallbackResult | None:
        """Resolve approximate match using URL slug and optional title hint."""
        parsed = urlparse(url)
        slug_tokens = self._tokenize(parsed.path.replace("-", " "))
        title_tokens = self._tokenize(title_hint or "")
        domain = extract_domain(url)
        feeds = self.get_candidate_feeds_for_domain(domain)

        best_item: FeedItem | None = None
        best_score = 0.0

        for item in self._iter_feed_items(feeds):
            item_tokens = self._tokenize(f"{item.title} {item.summary} {item.url}")
            if not item_tokens:
                continue

            slug_score = (
                len(slug_tokens & item_tokens) / max(1, len(slug_tokens))
                if slug_tokens
                else 0.0
            )
            title_score = (
                len(title_tokens & item_tokens) / max(1, len(title_tokens))
                if title_tokens
                else 0.0
            )
            score = max(slug_score, title_score * 0.9)

            if score > best_score:
                best_score = score
                best_item = item

        if best_item and best_score >= 0.45:
            return self._to_result(
                best_item, confidence=best_score, match_type="slug_title"
            )

        return None
