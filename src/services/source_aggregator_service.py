"""Source aggregation and preflight validation service."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

from src.core.config import settings
from src.core.exceptions import SourceExtractionError
from src.schemas.story_packet import StoryPacket
from src.services.balanced_source_planner import BalancedSourcePlanner, SourcePlan
from src.services.bias_resolution_service import (
    BiasResolutionInput,
    BiasResolutionService,
)
from src.services.duplicate_detector import check_duplicate
from src.services.relevance_scorer_service import RelevanceScorerService
from src.services.rss_fallback_service import RssFallbackResult, RssFallbackService
from src.services.source_scoring import ScoredCandidate, score_candidate
from src.tools.article_extractor import ArticleExtractor
from src.tools.bias_classifier import BiasResult
from src.tools.web_search import DuckDuckGoSearch, SearchResult, SearxngSearch

logger = logging.getLogger(__name__)

SOURCE_CONTEXT_EXCERPT_CHARS = 900
SOURCE_CONTEXT_MAX_CHARS = 7000


@dataclass
class SourceCandidate:
    """Represents a preflighted source candidate."""

    url: str
    domain: str
    title: str
    published_date: datetime | None
    author: str | None
    full_text: str
    extraction_error: str | None
    extraction_error_code: str | None = None
    extractor_method: str | None = None
    http_status: int | None = None
    bias_result: BiasResult | None = None
    relevance_score: float | None = None
    source_score: float | None = None
    bucket_label: str | None = None


class SourceAggregatorService:
    """Preflight sources before running CrewAI analysis.

    Integrates balanced source planning, duplicate detection, and
    coverage-aware stopping conditions.
    """

    MIN_TEXT_LENGTH = 200

    def __init__(self) -> None:
        self._extractor = ArticleExtractor()
        self._bias_resolver = BiasResolutionService()
        self._planner = BalancedSourcePlanner()
        self._relevance_scorer = RelevanceScorerService()
        self._searcher = self._init_searcher()
        self._rss_fallback = (
            RssFallbackService() if settings.rss_seed_fallback_enabled else None
        )
        self._last_seed_context_note: str | None = None
        self._missing_buckets: list[str] = []
        self._probed_count: int = 0
        self._duplicate_count: int = 0
        self._last_plan: SourcePlan | None = None

    def gather_sources(
        self,
        description: str,
        url: str | None,
        story_packet: StoryPacket | None = None,
    ) -> list[SourceCandidate]:
        """Gather and preflight sources based on description and optional URL."""
        if not description.strip() and not url:
            raise SourceExtractionError("Story description or URL is required.")

        self._missing_buckets = []
        self._probed_count = 0
        self._duplicate_count = 0
        self._last_plan = None

        sources: list[SourceCandidate] = []
        seen_urls: set[str] = set()
        seen_domains: set[str] = set()
        primary_error: str | None = None
        primary_error_code: str | None = None
        rss_hint: RssFallbackResult | None = None
        self._last_seed_context_note = None

        # Try extracting the provided URL first, but do not hard-fail if it is
        # blocked/paywalled; continue discovery from search in that case.
        if url:
            primary = self._extract_url(url, require_success=False)
            if primary.full_text and len(primary.full_text) >= self.MIN_TEXT_LENGTH:
                sources.append(primary)
                seen_urls.add(self._normalize_url(primary.url))
                seen_domains.add(primary.domain)
            else:
                primary_error = primary.extraction_error or "No content extracted"
                primary_error_code = primary.extraction_error_code
                logger.warning(
                    "Primary URL extraction failed for %s: %s (%s); continuing with discovery.",
                    url,
                    primary_error,
                    primary_error_code or "unknown",
                )
                if self._rss_fallback:
                    rss_hint = self._rss_fallback.resolve_by_url(url)
                    if not rss_hint:
                        rss_hint = self._rss_fallback.resolve_by_slug(url)

                if rss_hint:
                    self._last_seed_context_note = (
                        "SEED URL STATUS:\n"
                        f"- URL: {url}\n"
                        f"- Extraction blocked/failure: {primary_error_code or 'unknown'}\n"
                        f"- RSS metadata match ({rss_hint.match_type}, "
                        f"confidence={rss_hint.match_confidence:.2f})\n"
                        f"- Headline: {rss_hint.title}\n"
                        f"- Summary: {rss_hint.summary[:500]}\n"
                    )
                else:
                    self._last_seed_context_note = (
                        "SEED URL STATUS:\n"
                        f"- URL: {url}\n"
                        f"- Extraction blocked/failure: {primary_error_code or 'unknown'}\n"
                        "- RSS metadata fallback: not found\n"
                    )

        seed_bias = self._seed_bias(sources)
        seed_domain = sources[0].domain if sources else self._extract_domain(url or "")
        plan = self._planner.plan(seed_bias=seed_bias, seed_domain=seed_domain)
        self._last_plan = plan

        queries = self._build_queries(
            description,
            url,
            sources,
            rss_title=rss_hint.title if rss_hint else None,
            rss_summary=rss_hint.summary if rss_hint else None,
            story_packet=story_packet,
        )
        results = self._search_queries(queries, plan)
        scored_candidates = self._preflight_search_results(
            results=results,
            sources=sources,
            seen_urls=seen_urls,
            seen_domains=seen_domains,
            story_packet=story_packet,
            plan=plan,
        )

        self._select_scored_candidates(
            scored_candidates, sources, seen_urls, seen_domains, plan
        )

        if len(sources) < settings.retained_source_min:
            detail = f"Only {len(sources)} sources extracted; need at least {settings.retained_source_min}."
            if primary_error and not sources:
                detail += (
                    " Primary URL extraction failed: "
                    f"{primary_error} ({primary_error_code or 'unknown'})."
                )
            if rss_hint:
                detail += (
                    " RSS fallback found headline: "
                    f"'{rss_hint.title}' (confidence={rss_hint.match_confidence:.2f})."
                )
            elif self._rss_fallback and url:
                detail += " RSS fallback did not find matching entry."
            raise SourceExtractionError(detail)

        return sources

    def format_sources_context(self, sources: list[SourceCandidate]) -> str:
        """Format sources into a context block for CrewAI tasks."""
        lines = [
            "PREFETCHED SOURCES (Use ONLY these URLs).",
            "Use the excerpts as grounding; do not request or paste full article text.",
            "",
        ]
        if self._last_seed_context_note:
            lines.append(self._last_seed_context_note.strip()[:500])
        for i, src in enumerate(sources, 1):
            bias = src.bias_result
            bias_line = "Unknown"
            if bias:
                bias_line = f"{bias.bias} ({bias.bias_label}) via {bias.method}"
            excerpt = self._compact_text(src.full_text, SOURCE_CONTEXT_EXCERPT_CHARS)
            lines.append(
                "\n".join(
                    [
                        f"Source {i}:",
                        f"Title: {src.title}",
                        f"Domain: {src.domain}",
                        f"URL: {src.url}",
                        f"Bias: {bias_line}",
                        "Text Excerpt:",
                        excerpt,
                        "-" * 40,
                    ]
                )
            )
        context = "\n\n".join(lines)
        if len(context) <= SOURCE_CONTEXT_MAX_CHARS:
            return context
        return context[:SOURCE_CONTEXT_MAX_CHARS].rstrip() + "\n\n[Source context truncated]"

    def summarize_bias_spread(
        self, sources: list[SourceCandidate]
    ) -> dict[str, int | bool]:
        """Summarize left/right counts and whether bias spread is met."""
        left = sum(
            1
            for s in sources
            if s.bias_result and getattr(s.bias_result, "bias", 0) <= -2
        )
        right = sum(
            1
            for s in sources
            if s.bias_result and getattr(s.bias_result, "bias", 0) >= 2
        )
        return {
            "left_count": left,
            "right_count": right,
            "bias_spread_met": left > 0 and right > 0,
        }

    def summarize_coverage(self, sources: list[SourceCandidate]) -> dict:
        """Summarize coverage status including bucket details.

        Returns structured status: coverage_satisfied, missing_buckets,
        probed_count, retained_count, duplicate_count.
        """
        left = sum(
            1
            for s in sources
            if s.bias_result and getattr(s.bias_result, "bias", 0) <= -2
        )
        center = sum(
            1
            for s in sources
            if s.bias_result and abs(getattr(s.bias_result, "bias", 99)) <= 1
        )
        right = sum(
            1
            for s in sources
            if s.bias_result and getattr(s.bias_result, "bias", 0) >= 2
        )

        required_labels = (
            self._last_plan.required_labels
            if self._last_plan
            else ["left_side", "center", "right_side"]
        )
        filled_labels = {self._bucket_label(s) for s in sources}
        missing = [label for label in required_labels if label not in filled_labels]

        self._missing_buckets = missing

        return {
            "coverage_satisfied": len(missing) == 0,
            "missing_buckets": missing,
            "left_count": left,
            "center_count": center,
            "right_count": right,
            "probed_count": self._probed_count,
            "retained_count": len(sources),
            "duplicate_count": self._duplicate_count,
        }

    @property
    def missing_buckets(self) -> list[str]:
        """Return list of required but unfilled bias buckets."""
        return self._missing_buckets

    def _build_queries(
        self,
        description: str,
        url: str | None,
        sources: list[SourceCandidate],
        rss_title: str | None = None,
        rss_summary: str | None = None,
        story_packet: StoryPacket | None = None,
    ) -> list[str]:
        queries = []
        if story_packet:
            queries.extend(story_packet.query_pack)
            if story_packet.canonical_headline:
                queries.append(f'"{story_packet.canonical_headline}"')

        description = description.strip()
        if description:
            queries.append(description)

        if sources:
            title = sources[0].title.strip()
            if title:
                queries.append(f'"{title}"')
                if description:
                    queries.append(f"{title} {description}")

        if rss_title:
            queries.append(f'"{rss_title}"')
            if description:
                queries.append(f"{rss_title} {description}")
        if rss_summary:
            summary_terms = " ".join(self._extract_keywords(rss_summary)[:4])
            if summary_terms:
                queries.append(summary_terms)

        if url:
            slug_terms = self._slug_keywords(url)
            if slug_terms:
                queries.append(" ".join(slug_terms))

        # Deduplicate while preserving order
        seen = set()
        ordered = []
        for q in queries:
            key = q.lower()
            if key not in seen:
                seen.add(key)
                ordered.append(q)
        return ordered[:4]

    def _search_queries(
        self,
        queries: list[str],
        plan: SourcePlan | None = None,
    ) -> list[SearchResult]:
        results: list[SearchResult] = []
        seen_urls: set[str] = set()

        def add_results(found: list[SearchResult]) -> None:
            for result in found:
                normalized = self._normalize_url(result.url)
                if normalized in seen_urls:
                    continue
                seen_urls.add(normalized)
                results.append(result)

        for query in queries:
            if plan:
                for step in plan.search_plan:
                    phase = step.get("phase")
                    domains = step.get("domains") or []
                    if phase in {"rss_curated", "site_search"}:
                        for domain in domains:
                            site_query = f"site:{domain} {query}"
                            try:
                                if phase == "rss_curated":
                                    found = self._searcher.news_search(
                                        site_query,
                                        max_results=2,
                                        time_range=self._search_time_range(),
                                    )
                                else:
                                    found = self._searcher.web_search(
                                        site_query,
                                        max_results=2,
                                    )
                                add_results(found)
                            except Exception as exc:
                                logger.warning(
                                    "Search failed for '%s': %s", site_query, exc
                                )
                    elif phase == "open_web":
                        try:
                            found = self._searcher.news_search(
                                query,
                                max_results=12,
                                time_range=self._search_time_range(),
                            )
                            add_results(found)
                            if len(found) < 4:
                                fallback = self._searcher.web_search(
                                    query, max_results=8
                                )
                                add_results(fallback)
                        except Exception as exc:
                            logger.warning("Search failed for '%s': %s", query, exc)

                    if len(results) >= settings.candidate_probe_limit * 3:
                        break
                if len(results) >= settings.candidate_probe_limit * 3:
                    break
                continue

            try:
                found = self._searcher.news_search(
                    query,
                    max_results=12,
                    time_range=self._search_time_range(),
                )
                add_results(found)
                if len(found) < 4:
                    fallback = self._searcher.web_search(query, max_results=8)
                    add_results(fallback)
            except Exception as exc:
                logger.warning("Search failed for '%s': %s", query, exc)
        return results

    def _preflight_search_results(
        self,
        *,
        results: list[SearchResult],
        sources: list[SourceCandidate],
        seen_urls: set[str],
        seen_domains: set[str],
        story_packet: StoryPacket | None,
        plan: SourcePlan,
    ) -> list[tuple[ScoredCandidate, SourceCandidate]]:
        scored_candidates: list[tuple[ScoredCandidate, SourceCandidate]] = []
        candidate_urls = set(seen_urls)
        candidate_domains = set(seen_domains)

        for result in results:
            if self._probed_count >= settings.candidate_probe_limit:
                break

            candidate_url = result.url
            if not candidate_url.startswith("http"):
                continue
            normalized_url = self._normalize_url(candidate_url)
            domain = self._extract_domain(candidate_url)
            if normalized_url in candidate_urls or domain in candidate_domains:
                continue

            self._probed_count += 1
            candidate = self._extract_url(candidate_url, require_success=False)
            if not candidate or not candidate.full_text:
                continue
            if len(candidate.full_text) < self.MIN_TEXT_LENGTH:
                continue

            relevance_total = 0.5
            if story_packet:
                relevance = self._relevance_scorer.score(
                    candidate_title=candidate.title,
                    candidate_text=candidate.full_text,
                    candidate_date=candidate.published_date,
                    story_packet=story_packet,
                    seen_domains=candidate_domains,
                    candidate_domain=candidate.domain,
                )
                relevance_total = relevance.total
                candidate.relevance_score = relevance.total
                if relevance.rejection_reason:
                    logger.debug(
                        "Skipping low-relevance source %s: %s",
                        candidate.url,
                        relevance.rejection_reason,
                    )
                    continue

            existing_for_dedup = [
                {
                    "url": s.url,
                    "title": s.title,
                    "body_text": s.full_text[:500],
                    "domain": s.domain,
                }
                for s in sources
            ]
            dup_result = check_duplicate(
                candidate.url,
                candidate.title,
                candidate.full_text[:500],
                candidate.domain,
                existing_for_dedup,
            )
            if dup_result.is_duplicate:
                self._duplicate_count += 1
                logger.debug(
                    "Skipping duplicate %s: %s", candidate.url, dup_result.reason
                )
                continue

            bucket_label = self._bucket_label(candidate)
            candidate.bucket_label = bucket_label
            score = score_candidate(
                url=candidate.url,
                domain=candidate.domain,
                title=candidate.title,
                bias=getattr(candidate.bias_result, "bias", 0)
                if candidate.bias_result
                else 0,
                bucket_label=bucket_label,
                similarity=relevance_total,
                bucket_is_empty=self._bucket_is_empty(bucket_label, sources, plan),
                domain_already_present=candidate.domain in seen_domains,
                is_duplicate=False,
                published_date=candidate.published_date,
                reference_date=(
                    story_packet.time_window_start
                    if story_packet and story_packet.time_window_start
                    else None
                ),
            )
            candidate.source_score = score.total_score
            scored_candidates.append((score, candidate))
            candidate_urls.add(normalized_url)
            candidate_domains.add(domain)

        return scored_candidates

    def _select_scored_candidates(
        self,
        scored_candidates: list[tuple[ScoredCandidate, SourceCandidate]],
        sources: list[SourceCandidate],
        seen_urls: set[str],
        seen_domains: set[str],
        plan: SourcePlan,
    ) -> None:
        remaining = sorted(
            scored_candidates,
            key=lambda item: item[0].total_score,
            reverse=True,
        )

        while remaining and len(sources) < settings.retained_source_max:
            missing = set(self._missing_required_labels(sources, plan))
            if not missing and len(sources) >= settings.retained_source_min:
                break

            pool = [
                item
                for item in remaining
                if not missing or item[1].bucket_label in missing
            ] or remaining
            selected_score, selected = max(
                pool,
                key=lambda item: (
                    item[1].bucket_label in missing,
                    item[0].total_score,
                ),
            )
            remaining.remove((selected_score, selected))

            normalized_url = self._normalize_url(selected.url)
            if normalized_url in seen_urls or selected.domain in seen_domains:
                continue
            sources.append(selected)
            seen_urls.add(normalized_url)
            seen_domains.add(selected.domain)

    def _extract_url(self, url: str, require_success: bool = False) -> SourceCandidate:
        article = self._extractor.extract(url)
        if not article.success or len(article.text) < self.MIN_TEXT_LENGTH:
            if require_success:
                raise SourceExtractionError(
                    f"Failed to extract article from {url}: {article.error or 'No content'}"
                )
            return SourceCandidate(
                url=url,
                domain=self._extract_domain(url),
                title=article.title or "",
                published_date=article.date,
                author=article.author,
                full_text=article.text or "",
                extraction_error=article.error or "No content extracted",
                extraction_error_code=article.error_code,
                extractor_method=article.extractor_method,
                http_status=article.http_status,
                bias_result=None,
            )

        bias_result = self._resolve_bias(article.domain, url, article.text)

        return SourceCandidate(
            url=url,
            domain=article.domain,
            title=article.title or "",
            published_date=article.date,
            author=article.author,
            full_text=article.text or "",
            extraction_error=None,
            extraction_error_code=None,
            extractor_method=article.extractor_method,
            http_status=article.http_status,
            bias_result=bias_result,
        )

    def _resolve_bias(self, domain: str, url: str, text: str):
        if not domain:
            return None

        input_data = BiasResolutionInput(
            url=url,
            domain=domain,
            article_text=text,
            extra_texts=(),
        )

        def _extra_provider():
            extra_article = self._find_additional_article(domain, url, text)
            return [extra_article] if extra_article else []

        return self._bias_resolver.resolve(
            input_data, extra_texts_provider=_extra_provider
        )

    def _seed_bias(self, sources: list[SourceCandidate]) -> int | None:
        for source in sources:
            if source.bias_result:
                return getattr(source.bias_result, "bias", None)
        return None

    def _bucket_label(self, source: SourceCandidate) -> str:
        if source.bucket_label:
            return source.bucket_label
        if source.bias_result:
            return self._planner.classify_bias_to_bucket(
                getattr(source.bias_result, "bias", 0)
            )
        return "center"

    def _bucket_is_empty(
        self,
        bucket_label: str,
        sources: list[SourceCandidate],
        plan: SourcePlan,
    ) -> bool:
        return bucket_label in self._missing_required_labels(sources, plan)

    def _missing_required_labels(
        self,
        sources: list[SourceCandidate],
        plan: SourcePlan,
    ) -> list[str]:
        filled = {self._bucket_label(source) for source in sources}
        return [label for label in plan.required_labels if label not in filled]

    def _search_time_range(self) -> str:
        days = getattr(settings, "search_time_window_days", 7)
        if not isinstance(days, int):
            days = 7
        if days <= 1:
            return "d"
        if days <= 7:
            return "w"
        return "m"

    def _find_additional_article(self, domain: str, url: str, text: str) -> str | None:
        keywords = self._extract_keywords(text)
        if not keywords:
            return None
        query = f"site:{domain} " + " ".join(keywords[:3])
        try:
            results = self._searcher.web_search(query, max_results=5)
        except Exception:
            return None

        for result in results:
            if not result.url.startswith("http"):
                continue
            if self._normalize_url(result.url) == self._normalize_url(url):
                continue
            article = self._extractor.extract(result.url)
            if article.success and len(article.text) >= self.MIN_TEXT_LENGTH:
                return article.text
        return None

    def _bias_spread_met(self, sources: list[SourceCandidate]) -> bool:
        """Check if bias coverage requirements are met.

        Uses explicit bucket group checks (left, center, right)
        instead of the old any-left-any-right approach.
        """
        has_left = any(
            s.bias_result and getattr(s.bias_result, "bias", 0) <= -2 for s in sources
        )
        has_center = any(
            s.bias_result and abs(getattr(s.bias_result, "bias", 99)) <= 1
            for s in sources
        )
        has_right = any(
            s.bias_result and getattr(s.bias_result, "bias", 0) >= 2 for s in sources
        )
        return (
            has_left
            and has_center
            and has_right
            and len(sources) >= settings.retained_source_min
        )

    def _slug_keywords(self, url: str) -> list[str]:
        try:
            path = urlparse(url).path
        except Exception:
            return []
        parts = [p for p in path.split("/") if p]
        slug = "-".join(parts[-2:]) if parts else ""
        tokens = re.split(r"[^a-zA-Z0-9]+", slug.lower())
        stop = {"the", "a", "an", "and", "or", "of", "to", "in", "for"}
        return [t for t in tokens if t and t not in stop][:6]

    def _extract_keywords(self, text: str) -> list[str]:
        # Best-effort keyword extraction without hard dependency on YAKE
        try:
            from src.tools.keyword_extractor import KeywordExtractor

            extractor = KeywordExtractor()
            keywords = extractor.extract(text, top_n=5)
            return [kw.term for kw in keywords if kw.term]
        except Exception:
            # Fallback: simple word frequency
            tokens = re.findall(r"[a-zA-Z]{4,}", text.lower())
            freq: dict[str, int] = {}
            for token in tokens[:500]:
                freq[token] = freq.get(token, 0) + 1
            ranked = sorted(freq.items(), key=lambda x: x[1], reverse=True)
            return [term for term, _ in ranked[:5]]

    def _init_searcher(self):
        if settings.searxng_base_url:
            return SearxngSearch(settings.searxng_base_url, settings.searxng_api_key)
        return DuckDuckGoSearch()

    def _extract_domain(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            return parsed.netloc.replace("www.", "")
        except Exception:
            return ""

    def _normalize_url(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            path = parsed.path.rstrip("/")
            return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"
        except Exception:
            return url.lower().rstrip("/")

    def _compact_text(self, text: str, max_chars: int) -> str:
        compacted = re.sub(r"\s+", " ", text or "").strip()
        if len(compacted) <= max_chars:
            return compacted
        return compacted[:max_chars].rstrip() + "..."
