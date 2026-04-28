"""Source aggregation and preflight validation service."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

from src.core.config import settings
from src.core.exceptions import SourceExtractionError
from src.services.bias_resolution_service import BiasResolutionInput, BiasResolutionService
from src.services.rss_fallback_service import RssFallbackResult, RssFallbackService
from src.tools.article_extractor import ArticleExtractor
from src.tools.bias_classifier import BiasResult
from src.tools.web_search import DuckDuckGoSearch, SearchResult, SearxngSearch

logger = logging.getLogger(__name__)


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


class SourceAggregatorService:
    """Preflight sources before running CrewAI analysis."""

    MIN_SOURCES = 2
    MAX_SOURCES = 5
    MIN_TEXT_LENGTH = 200

    def __init__(self) -> None:
        self._extractor = ArticleExtractor()
        self._bias_resolver = BiasResolutionService()
        self._searcher = self._init_searcher()
        self._rss_fallback = (
            RssFallbackService() if settings.rss_seed_fallback_enabled else None
        )
        self._last_seed_context_note: str | None = None

    def gather_sources(self, description: str, url: str | None) -> list[SourceCandidate]:
        """Gather and preflight sources based on description and optional URL."""
        if not description.strip() and not url:
            raise SourceExtractionError("Story description or URL is required.")

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

        queries = self._build_queries(
            description,
            url,
            sources,
            rss_title=rss_hint.title if rss_hint else None,
            rss_summary=rss_hint.summary if rss_hint else None,
        )
        results = self._search_queries(queries)

        for result in results:
            if len(sources) >= self.MAX_SOURCES:
                break
            if self._bias_spread_met(sources):
                break

            candidate_url = result.url
            if not candidate_url.startswith("http"):
                continue
            normalized_url = self._normalize_url(candidate_url)
            domain = self._extract_domain(candidate_url)
            if normalized_url in seen_urls or domain in seen_domains:
                continue

            candidate = self._extract_url(candidate_url, require_success=False)
            if not candidate or not candidate.full_text:
                continue

            if len(candidate.full_text) < self.MIN_TEXT_LENGTH:
                continue

            sources.append(candidate)
            seen_urls.add(normalized_url)
            seen_domains.add(domain)

        if len(sources) < self.MIN_SOURCES:
            detail = (
                f"Only {len(sources)} sources extracted; need at least {self.MIN_SOURCES}."
            )
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
            raise SourceExtractionError(
                detail
            )

        return sources

    def format_sources_context(self, sources: list[SourceCandidate]) -> str:
        """Format sources into a context block for CrewAI tasks."""
        lines = ["PREFETCHED SOURCES (Use ONLY these URLs):\n"]
        if self._last_seed_context_note:
            lines.append(self._last_seed_context_note.strip())
        for i, src in enumerate(sources, 1):
            bias = src.bias_result
            bias_line = "Unknown"
            if bias:
                bias_line = f"{bias.bias} ({bias.bias_label}) via {bias.method}"
            excerpt = (src.full_text or "")[:2000].strip()
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
        return "\n\n".join(lines)

    def summarize_bias_spread(self, sources: list[SourceCandidate]) -> dict[str, int | bool]:
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
    def _build_queries(
        self,
        description: str,
        url: str | None,
        sources: list[SourceCandidate],
        rss_title: str | None = None,
        rss_summary: str | None = None,
    ) -> list[str]:
        queries = []
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

    def _search_queries(self, queries: list[str]) -> list[SearchResult]:
        results: list[SearchResult] = []
        for query in queries:
            try:
                found = self._searcher.news_search(query, max_results=12, time_range="m")
                results.extend(found)
                if len(found) < 4:
                    fallback = self._searcher.web_search(query, max_results=8)
                    results.extend(fallback)
            except Exception as exc:
                logger.warning("Search failed for '%s': %s", query, exc)
        return results

    def _extract_url(
        self, url: str, require_success: bool = False
    ) -> SourceCandidate:
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

        return self._bias_resolver.resolve(input_data, extra_texts_provider=_extra_provider)

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
        left = any(
            s.bias_result and getattr(s.bias_result, "bias", 0) <= -2 for s in sources
        )
        right = any(
            s.bias_result and getattr(s.bias_result, "bias", 0) >= 2 for s in sources
        )
        return left and right and len(sources) >= self.MIN_SOURCES

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
