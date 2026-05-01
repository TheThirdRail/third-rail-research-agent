"""Analysis-time RSS retrieval for curated source gathering."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

from src.core.config import settings
from src.schemas.story_packet import StoryPacket
from src.services.balanced_source_planner import BucketSpec
from src.tools.rss_aggregator import FeedItem, RSSAggregator
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

    def search_story(
        self,
        packet: StoryPacket,
        bucket_spec: BucketSpec,
        *,
        max_results: int = 8,
    ) -> list[SearchResult]:
        """Return RSS feed items that match the structured story identity."""
        if not self.aggregator or not bucket_spec.domain_targets:
            return []

        results: list[SearchResult] = []
        feed_attempts = 0
        max_feed_attempts = max(
            1,
            self._setting_int("analysis_rss_max_feeds_per_bucket", 3),
        )
        timeout_seconds = max(1, self._setting_int("analysis_rss_timeout_seconds", 6))
        min_score = self._setting_float("rss_candidate_min_story_score", 0.45)
        target_domains = {
            self._normalize_domain(domain) for domain in bucket_spec.domain_targets
        }

        for feed in self.aggregator.feeds:
            if len(results) >= max_results or feed_attempts >= max_feed_attempts:
                break
            feed_url = str(feed.get("url", ""))
            if not self._valid_feed_url(feed_url):
                continue
            feed_domain = self._normalize_domain(feed_url)
            source_name = str(feed.get("name", "Unknown"))
            if not self._feed_matches_targets(feed_domain, source_name, target_domains):
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
                score = self._score_story_item(item, packet)
                if score < min_score:
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

    def _score_story_item(self, item: FeedItem, packet: StoryPacket) -> float:
        title = item.title or ""
        summary = item.summary or ""
        title_text = title.lower()
        full_text = f"{title} {summary}".lower()

        if self._contains_any(full_text, packet.must_not_have_terms):
            return 0.0

        title_overlap = self._term_overlap(
            title_text, self._query_terms(packet.canonical_headline)
        )
        headline_overlap = self._term_overlap(
            full_text, self._query_terms(packet.canonical_headline)
        )
        actor_overlap = self._term_overlap(full_text, packet.actors + packet.aliases)
        verb_overlap = self._term_overlap(full_text, packet.action_verbs)
        distinctive_overlap = self._term_overlap(
            full_text,
            packet.distinctive_terms + packet.visual_descriptors,
        )
        date_overlap = self._date_overlap(item.published, packet)
        marker_overlap = self._marker_overlap(full_text, packet)

        summary_only_penalty = 0.0
        if title_overlap == 0 and headline_overlap > 0:
            summary_only_penalty = 0.18

        score = (
            title_overlap * 0.24
            + headline_overlap * 0.18
            + actor_overlap * 0.18
            + verb_overlap * 0.12
            + distinctive_overlap * 0.16
            + date_overlap * 0.07
            + marker_overlap * 0.05
            - summary_only_penalty
        )
        return max(0.0, min(1.0, score))

    @classmethod
    def _marker_overlap(cls, text: str, packet: StoryPacket) -> float:
        markers = (
            packet.quote_markers
            + packet.number_markers
            + packet.platform_markers
        )
        for term in packet.distinctive_terms + packet.visual_descriptors:
            if re.search(r"\d|['\"@#]", term) or term.lower() in {
                "x",
                "twitter",
                "instagram",
                "threads",
                "facebook",
                "tiktok",
                "truth social",
            }:
                markers.append(term)
        return cls._term_overlap(text, markers)

    @staticmethod
    def _date_overlap(published: datetime | None, packet: StoryPacket) -> float:
        if not published or not packet.time_window_start:
            return 0.0
        start = packet.time_window_start.replace(tzinfo=None)
        end = (packet.time_window_end or packet.time_window_start).replace(tzinfo=None)
        published = published.replace(tzinfo=None)
        return 1.0 if start <= published <= end else 0.0

    @classmethod
    def _term_overlap(cls, text: str, terms: list[str]) -> float:
        normalized = [term.lower().strip() for term in terms if term.strip()]
        if not normalized:
            return 0.0
        hits = sum(1 for term in normalized if cls._term_in_text(term, text))
        return hits / len(normalized)

    @staticmethod
    def _contains_any(text: str, terms: list[str]) -> bool:
        return any(
            term.lower().strip() and term.lower().strip() in text for term in terms
        )

    @staticmethod
    def _term_in_text(term: str, text: str) -> bool:
        if " " in term:
            return term in text
        return re.search(rf"\b{re.escape(term)}\b", text) is not None

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
    def _setting_float(name: str, default: float) -> float:
        value = getattr(settings, name, default)
        return value if isinstance(value, int | float) else default

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
