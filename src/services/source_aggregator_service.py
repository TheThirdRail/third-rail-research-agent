"""Source aggregation and preflight validation service."""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

from src.core.config import settings
from src.core.embedding_provider import EmbeddingProvider
from src.core.exceptions import SourceExtractionError
from src.schemas.retrieval_diagnostics import (
    BucketLaneAttempt,
    CandidateCensus,
    CandidateDecision,
    MissingBucketExplanation,
)
from src.schemas.story_packet import StoryPacket
from src.schemas.visual_evidence import MediaPointer
from src.services.balanced_source_planner import (
    BalancedSourcePlanner,
    BucketSpec,
    SourcePlan,
)
from src.services.bias_resolution_service import (
    BiasResolutionInput,
    BiasResolutionService,
)
from src.services.candidate_semantic_scorer import CandidateSemanticScorer
from src.services.duplicate_detector import check_duplicate
from src.services.relevance_scorer_service import RelevanceScorerService
from src.services.rss_fallback_service import RssFallbackResult, RssFallbackService
from src.services.rss_retrieval_service import RssRetrievalService
from src.services.source_scoring import ScoredCandidate, score_candidate
from src.tools.article_extractor import ArticleExtractor
from src.tools.bias_classifier import BiasResult
from src.tools.web_search import DuckDuckGoSearch, SearchResult, SearxngSearch
from src.utils.url_utils import extract_domain

logger = logging.getLogger(__name__)

SOURCE_CONTEXT_EXCERPT_CHARS = 900
SOURCE_CONTEXT_MAX_CHARS = 7000

MAX_QUERIES_PER_FAMILY: dict[str, int] = {
    "canonical_headline": 2,
    "lexical": 4,
    "semantic_paraphrase": 4,
    "opposing_frame": 4,
    "visual_social": 4,
    "description": 1,
    "seed_title": 2,
    "rss_title": 2,
    "rss_summary": 2,
    "url_slug": 2,
}


@dataclass(frozen=True)
class QueryAttempt:
    """A single query tagged with its family for scheduling."""

    query: str
    family: str
    priority: int = 0
    source: str = "story_packet"


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
    semantic_similarity: float | None = None
    semantic_title_similarity: float | None = None
    semantic_lede_similarity: float | None = None
    semantic_chunk_similarity: float | None = None
    distinctive_term_overlap: float | None = None
    direct_evidence_score: float | None = None
    source_score: float | None = None
    bucket_label: str | None = None
    coverage_type: str | None = None
    og_image_url: str | None = None
    embedded_post_urls: tuple[str, ...] = ()
    image_alt_text: tuple[str, ...] = ()
    media_captions: tuple[str, ...] = ()


class SourceAggregatorService:
    """Preflight sources before running CrewAI analysis.

    Integrates balanced source planning, duplicate detection, and
    coverage-aware stopping conditions.
    """

    MIN_TEXT_LENGTH = 200

    def __init__(
        self,
        *,
        settings_overrides: dict[str, object] | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._settings_overrides = settings_overrides or {}
        self._embedding_provider = embedding_provider
        self._extractor = ArticleExtractor()
        self._bias_resolver = BiasResolutionService()
        self._planner = BalancedSourcePlanner(
            settings_overrides=self._settings_overrides
        )
        self._relevance_scorer = RelevanceScorerService()
        self._searcher = self._init_searcher()
        self._rss_retriever = RssRetrievalService()
        self._rss_fallback = (
            RssFallbackService() if settings.rss_seed_fallback_enabled else None
        )
        self._last_seed_context_note: str | None = None
        self._missing_buckets: list[str] = []
        self._probed_count: int = 0
        self._duplicate_count: int = 0
        self._last_plan: SourcePlan | None = None
        self._candidate_decisions: list[CandidateDecision] = []
        self._bucket_lane_attempts: list[BucketLaneAttempt] = []
        self._result_stage_by_url: dict[str, str] = {}
        self._result_bucket_by_url: dict[str, str] = {}
        self._rss_story_diagnostics_by_url: dict[str, dict[str, object]] = {}

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
        self._candidate_decisions = []
        self._bucket_lane_attempts = []
        self._result_stage_by_url = {}
        self._result_bucket_by_url = {}

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
                self._record_primary_decision(primary, state="retained")
            else:
                primary_error = primary.extraction_error or "No content extracted"
                primary_error_code = primary.extraction_error_code
                self._record_primary_decision(
                    primary,
                    state="extraction_failed",
                    rejection_reason=(
                        "extracted_text_too_short"
                        if primary.full_text
                        else "no_extracted_text"
                    ),
                )
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
        seed_domain = sources[0].domain if sources else extract_domain(url or "")
        plan = self._planner.plan(seed_bias=seed_bias, seed_domain=seed_domain)
        self._last_plan = plan

        query_attempts = self._build_query_attempts(
            description,
            url,
            sources,
            rss_title=rss_hint.title if rss_hint else None,
            rss_summary=rss_hint.summary if rss_hint else None,
            story_packet=story_packet,
        )
        results = self._search_queries(query_attempts, plan, story_packet)
        scored_candidates = self._preflight_search_results(
            results=results,
            description=description,
            sources=sources,
            seen_urls=seen_urls,
            seen_domains=seen_domains,
            story_packet=story_packet,
            plan=plan,
        )

        self._select_scored_candidates(
            scored_candidates, sources, seen_urls, seen_domains, plan
        )

        self._missing_buckets = self._missing_required_labels(sources, plan)
        if (
            self._setting_bool("strict_bucket_enforcement", True)
            and self._missing_buckets
        ):
            raise SourceExtractionError(
                "Missing required ideological coverage: "
                + ", ".join(self._missing_buckets)
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
                        self._format_media_context(src),
                        "Text Excerpt:",
                        excerpt,
                        "-" * 40,
                    ]
                )
            )
        context = "\n\n".join(lines)
        if len(context) <= SOURCE_CONTEXT_MAX_CHARS:
            return context
        return (
            context[:SOURCE_CONTEXT_MAX_CHARS].rstrip()
            + "\n\n[Source context truncated]"
        )

    def collect_media_pointers(
        self,
        sources: list[SourceCandidate],
    ) -> list[MediaPointer]:
        """Collect media pointers from extracted sources for visual evidence."""
        pointers: list[MediaPointer] = []
        for source in sources:
            if source.og_image_url:
                pointers.append(
                    MediaPointer(
                        source_url=source.url,
                        media_url=source.og_image_url,
                        media_type="image",
                        alt_text="; ".join(source.image_alt_text[:3]),
                        caption="; ".join(source.media_captions[:3]),
                    )
                )
            for post_url in source.embedded_post_urls:
                pointers.append(
                    MediaPointer(
                        source_url=source.url,
                        media_url=post_url,
                        media_type="social_post",
                        platform=self._platform_from_url(post_url),
                        alt_text="; ".join(source.image_alt_text[:3]),
                        caption="; ".join(source.media_captions[:3]),
                    )
                )
        return pointers[:10]

    def summarize_bias_spread(
        self, sources: list[SourceCandidate]
    ) -> dict[str, int | bool]:
        """Summarize left/right counts and whether bias spread is met."""
        left = sum(
            1
            for s in sources
            if s.bias_result and getattr(s.bias_result, "bias", 0) <= -1
        )
        right = sum(
            1
            for s in sources
            if s.bias_result and getattr(s.bias_result, "bias", 0) >= 1
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
            if s.bias_result and getattr(s.bias_result, "bias", 0) <= -1
        )
        center = sum(
            1
            for s in sources
            if s.bias_result and getattr(s.bias_result, "bias", 99) == 0
        )
        right = sum(
            1
            for s in sources
            if s.bias_result and getattr(s.bias_result, "bias", 0) >= 1
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
            "exact_bias_counts": self._exact_bias_counts(sources),
            "bucket_counts": self._bucket_counts(sources),
            "probed_count": self._probed_count,
            "retained_count": len(sources),
            "duplicate_count": self._duplicate_count,
            "candidate_census": self.candidate_census(
                missing_buckets=missing
            ).model_dump(mode="json"),
        }

    @property
    def candidate_decisions(self) -> list[CandidateDecision]:
        """Return terminal lifecycle decisions from the last gather run."""
        return list(self._candidate_decisions)

    def candidate_census(
        self, *, missing_buckets: list[str] | None = None
    ) -> CandidateCensus:
        """Return aggregate lifecycle counts from the last gather run."""
        missing = list(missing_buckets or [])
        return CandidateCensus.from_decisions(
            self._candidate_decisions,
            missing_buckets=missing,
            missing_bucket_explanations=self._missing_bucket_explanations(missing),
            bucket_lane_attempts=self._bucket_lane_attempts,
        )

    def _missing_bucket_explanations(
        self,
        missing_buckets: list[str],
    ) -> list[MissingBucketExplanation]:
        explanations: list[MissingBucketExplanation] = []
        for bucket in missing_buckets:
            decisions = [
                decision
                for decision in self._candidate_decisions
                if decision.bucket_label == bucket
            ]
            state_counts = Counter(decision.state for decision in decisions)
            rejection_counts = Counter(
                decision.rejection_reason
                for decision in decisions
                if decision.rejection_reason
            )
            if not decisions:
                reason = "no_candidates_probed"
            elif state_counts and state_counts.total() == state_counts.get(
                "extraction_failed", 0
            ):
                reason = "all_candidates_failed_extraction"
            elif state_counts and state_counts.total() == state_counts.get(
                "relevance_rejected", 0
            ):
                reason = "all_candidates_relevance_rejected"
            elif state_counts and state_counts.total() == state_counts.get(
                "policy_rejected", 0
            ):
                reason = "all_candidates_policy_rejected"
            elif state_counts.get("extracted", 0) or state_counts.get(
                "duplicate_rejected", 0
            ):
                reason = "candidates_available_but_not_retained"
            else:
                reason = "bucket_not_retained"

            explanations.append(
                MissingBucketExplanation(
                    bucket_label=bucket,
                    reason=reason,
                    probed_count=len(decisions),
                    by_state=dict(state_counts),
                    rejection_reasons=dict(rejection_counts),
                    probe_limit_reached=(
                        self._probed_count >= settings.candidate_probe_limit
                    ),
                )
            )
        return explanations

    @property
    def missing_buckets(self) -> list[str]:
        """Return list of required but unfilled bias buckets."""
        return self._missing_buckets

    def _build_query_attempts(
        self,
        description: str,
        url: str | None,
        sources: list[SourceCandidate],
        rss_title: str | None = None,
        rss_summary: str | None = None,
        story_packet: StoryPacket | None = None,
    ) -> list[QueryAttempt]:
        attempts: list[QueryAttempt] = []

        if story_packet and story_packet.query_families:
            for family, family_queries in story_packet.query_families.items():
                cap = MAX_QUERIES_PER_FAMILY.get(family, 4)
                for q in family_queries[:cap]:
                    attempts.append(
                        QueryAttempt(query=q, family=family, source="story_packet")
                    )
            # Add canonical_headline as its own family entry
            if story_packet.canonical_headline:
                attempts.append(
                    QueryAttempt(
                        query=f'"{story_packet.canonical_headline}"',
                        family="canonical_headline",
                        source="story_packet",
                    )
                )
        elif story_packet:
            # Fallback: no query_families, use query_pack as lexical
            for q in story_packet.query_pack:
                attempts.append(
                    QueryAttempt(query=q, family="lexical", source="query_pack")
                )
            if story_packet.canonical_headline:
                attempts.append(
                    QueryAttempt(
                        query=f'"{story_packet.canonical_headline}"',
                        family="canonical_headline",
                        source="story_packet",
                    )
                )

        description = description.strip()
        if description:
            attempts.append(
                QueryAttempt(query=description, family="description", source="input")
            )

        if sources:
            title = sources[0].title.strip()
            if title:
                attempts.append(
                    QueryAttempt(
                        query=f'"{title}"',
                        family="seed_title",
                        source="input",
                    )
                )
                if description:
                    attempts.append(
                        QueryAttempt(
                            query=f"{title} {description}",
                            family="seed_title",
                            source="input",
                        )
                    )

        if rss_title:
            attempts.append(
                QueryAttempt(
                    query=f'"{rss_title}"',
                    family="rss_title",
                    source="rss_hint",
                )
            )
            if description:
                attempts.append(
                    QueryAttempt(
                        query=f"{rss_title} {description}",
                        family="rss_title",
                        source="rss_hint",
                    )
                )
        if rss_summary:
            summary_terms = " ".join(self._extract_keywords(rss_summary)[:4])
            if summary_terms:
                attempts.append(
                    QueryAttempt(
                        query=summary_terms,
                        family="rss_summary",
                        source="rss_hint",
                    )
                )

        if url:
            slug_terms = self._slug_keywords(url)
            if slug_terms:
                attempts.append(
                    QueryAttempt(
                        query=" ".join(slug_terms),
                        family="url_slug",
                        source="input",
                    )
                )

        # Deduplicate per family while preserving order
        seen: set[str] = set()
        family_counts: dict[str, int] = {}
        deduped: list[QueryAttempt] = []
        for attempt in attempts:
            key = attempt.query.lower()
            if key in seen:
                continue
            cap = MAX_QUERIES_PER_FAMILY.get(attempt.family, 4)
            if family_counts.get(attempt.family, 0) >= cap:
                continue
            seen.add(key)
            family_counts[attempt.family] = family_counts.get(attempt.family, 0) + 1
            deduped.append(attempt)
        return deduped

    def _query_attempts_for_phase(
        self, attempts: list[QueryAttempt], phase: str
    ) -> list[QueryAttempt]:
        """Filter query attempts to families allowed in a given phase.

        Non-story_packet sources (rss_hint, input, query_pack) bypass
        phase filtering for backward compatibility when query_families
        were not available.
        """
        allowed: dict[str, set[str]] = {
            "rss": {
                "canonical_headline",
                "lexical",
                "rss_title",
                "seed_title",
            },
            "site_search": {
                "canonical_headline",
                "lexical",
                "opposing_frame",
                "url_slug",
            },
            "open_web": {
                "canonical_headline",
                "lexical",
                "semantic_paraphrase",
                "opposing_frame",
                "visual_social",
                "description",
            },
            "visual_social": {"visual_social", "canonical_headline"},
        }
        families = allowed.get(phase)
        if families is None:
            return attempts
        return [
            a for a in attempts if a.source != "story_packet" or a.family in families
        ]

    def _search_queries(
        self,
        query_attempts: list[QueryAttempt],
        plan: SourcePlan | None = None,
        story_packet: StoryPacket | None = None,
    ) -> list[SearchResult]:
        results: list[SearchResult] = []
        seen_urls: set[str] = set()

        def add_results(
            found: list[SearchResult],
            stage: str = "open_web",
            bucket_label: str | None = None,
        ) -> None:
            for result in found:
                normalized = self._normalize_url(result.url)
                if normalized in seen_urls:
                    continue
                seen_urls.add(normalized)
                self._result_stage_by_url[normalized] = stage
                if bucket_label:
                    self._result_bucket_by_url[normalized] = bucket_label
                results.append(result)

        if plan:
            return self._search_queries_by_bucket_round_robin(
                query_attempts,
                plan,
                story_packet,
                add_results,
                results,
            )

        for attempt in query_attempts:
            try:
                found = self._searcher.news_search(
                    attempt.query,
                    max_results=12,
                    time_range=self._search_time_range(),
                )
                add_results(found, "open_web")
                if len(found) < 4:
                    fallback = self._searcher.web_search(attempt.query, max_results=8)
                    add_results(fallback, "open_web")
            except Exception as exc:
                logger.warning("Search failed for '%s': %s", attempt.query, exc)
        return results

    def _search_queries_by_bucket_round_robin(
        self,
        query_attempts: list[QueryAttempt],
        plan: SourcePlan,
        story_packet: StoryPacket | None,
        add_results,
        results: list[SearchResult],
    ) -> list[SearchResult]:
        steps_by_bucket: dict[str, list[dict[str, object]]] = {}
        for step in plan.search_plan:
            bucket = str(step.get("bucket") or "")
            if not bucket:
                continue
            steps_by_bucket.setdefault(bucket, []).append(step)

        bucket_result_counts = dict.fromkeys(steps_by_bucket, 0)
        max_results_total = settings.candidate_probe_limit * 3
        bucket_specs = {bucket.label: bucket for bucket in plan.all_buckets}

        for attempt in query_attempts:
            for bucket_label in plan.bucket_probe_sequence:
                if len(results) >= max_results_total:
                    self._record_unattempted_bucket_lanes(
                        attempt.query,
                        steps_by_bucket.get(bucket_label, []),
                        "global_result_limit_reached",
                        query_family=attempt.family,
                    )
                    return results
                quota = bucket_specs.get(bucket_label)
                if (
                    quota
                    and bucket_result_counts.get(bucket_label, 0) >= quota.probe_quota
                ):
                    self._record_unattempted_bucket_lanes(
                        attempt.query,
                        steps_by_bucket.get(bucket_label, []),
                        "bucket_probe_quota_reached",
                        query_family=attempt.family,
                    )
                    continue
                # Filter steps by phase compatibility with query family
                phase_steps = steps_by_bucket.get(bucket_label, [])
                for step in phase_steps:
                    phase = str(step.get("phase") or "")
                    phase_attempts = self._query_attempts_for_phase([attempt], phase)
                    if not phase_attempts:
                        continue
                    before = len(results)
                    new_count = self._search_plan_step(
                        attempt.query,
                        step,
                        story_packet,
                        plan,
                        add_results,
                    )
                    bucket_result_counts[bucket_label] = bucket_result_counts.get(
                        bucket_label, 0
                    ) + max(0, len(results) - before)
                    self._record_bucket_lane_attempt(
                        query=attempt.query,
                        step=step,
                        result_count=new_count,
                        new_result_count=max(0, len(results) - before),
                        query_family=attempt.family,
                    )
                    if len(results) >= max_results_total:
                        return results
                    if (
                        quota
                        and bucket_result_counts.get(bucket_label, 0)
                        >= quota.probe_quota
                    ):
                        break
        return results

    def _search_plan_step(
        self,
        query: str,
        step: dict[str, object],
        story_packet: StoryPacket | None,
        plan: SourcePlan | None,
        add_results,
    ) -> int:
        found_count = 0

        def add_found(found: list[SearchResult], stage: str) -> None:
            nonlocal found_count
            found_count += len(found)
            try:
                add_results(found, stage, str(step.get("bucket") or "") or None)
            except TypeError:
                add_results(found)

        phase = step.get("phase")
        domains = step.get("domains") or []
        if phase == "rss":
            if not self._setting_bool("analysis_rss_first_enabled", True):
                return 0
            try:
                bucket_spec = self._bucket_spec(plan, str(step.get("bucket") or ""))
                if story_packet and bucket_spec:
                    found = self._rss_retriever.search_story(
                        story_packet,
                        bucket_spec,
                        max_results=8,
                    )
                    self._capture_rss_story_diagnostics()
                else:
                    found = self._rss_retriever.search(
                        query,
                        domains=list(domains),
                        max_results=8,
                    )
                add_found(found, "rss")
            except Exception as exc:
                logger.warning("RSS retrieval failed for '%s': %s", query, exc)
        elif phase == "site_search":
            for domain in domains:
                site_query = f"site:{domain} {query}"
                try:
                    found = self._searcher.web_search(site_query, max_results=2)
                    add_found(found, "site_search")
                except Exception as exc:
                    logger.warning("Search failed for '%s': %s", site_query, exc)
        elif phase == "open_web":
            try:
                found = self._searcher.news_search(
                    query,
                    max_results=12,
                    time_range=self._search_time_range(),
                )
                add_found(found, "open_web")
                if len(found) < 4:
                    fallback = self._searcher.web_search(query, max_results=8)
                    add_found(fallback, "open_web")
            except Exception as exc:
                logger.warning("Search failed for '%s': %s", query, exc)
        return found_count

    def _record_unattempted_bucket_lanes(
        self,
        query: str,
        steps: list[dict[str, object]],
        reason: str,
        query_family: str | None = None,
    ) -> None:
        for step in steps:
            self._record_bucket_lane_attempt(
                query=query,
                step=step,
                result_count=0,
                new_result_count=0,
                exhausted_reason=reason,
                query_family=query_family,
            )

    def _record_bucket_lane_attempt(
        self,
        *,
        query: str,
        step: dict[str, object],
        result_count: int,
        new_result_count: int,
        exhausted_reason: str | None = None,
        query_family: str | None = None,
    ) -> None:
        phase = str(step.get("phase") or "unknown")
        if phase not in {"rss", "site_search", "open_web"}:
            phase = "unknown"
        domains = step.get("domains") or []
        self._bucket_lane_attempts.append(
            BucketLaneAttempt(
                bucket_label=str(step.get("bucket") or ""),
                stage=phase,
                query=query,
                query_family=query_family,
                exact_bias=step.get("exact_bias")
                if isinstance(step.get("exact_bias"), int)
                else None,
                domains=[str(domain) for domain in domains],
                result_count=result_count,
                new_result_count=new_result_count,
                exhausted_reason=exhausted_reason
                or ("no_results" if result_count == 0 else None),
            )
        )

    @staticmethod
    def _bucket_spec(plan: SourcePlan | None, label: str) -> BucketSpec | None:
        if not plan:
            return None
        for bucket in plan.all_buckets:
            if bucket.label == label:
                return bucket
        return None

    def _preflight_search_results(
        self,
        *,
        results: list[SearchResult],
        description: str,
        sources: list[SourceCandidate],
        seen_urls: set[str],
        seen_domains: set[str],
        story_packet: StoryPacket | None,
        plan: SourcePlan,
    ) -> list[tuple[ScoredCandidate, SourceCandidate]]:
        scored_candidates: list[tuple[ScoredCandidate, SourceCandidate]] = []
        candidate_urls = set(seen_urls)
        candidate_domains = set(seen_domains)
        semantic_scorer = self._build_candidate_semantic_scorer(
            story_packet, description
        )

        for result in results:
            if self._probed_count >= settings.candidate_probe_limit:
                break

            candidate_url = result.url
            if not candidate_url.startswith("http"):
                continue
            normalized_url = self._normalize_url(candidate_url)
            domain = extract_domain(candidate_url)
            stage = self._result_stage_by_url.get(normalized_url, "open_web")
            planned_bucket = self._result_bucket_by_url.get(normalized_url)
            if normalized_url in candidate_urls or domain in candidate_domains:
                continue

            self._probed_count += 1
            candidate = self._extract_url(candidate_url, require_success=False)
            if not candidate or not candidate.full_text:
                self._record_candidate_decision(
                    candidate=candidate,
                    result=result,
                    stage=stage,
                    state="extraction_failed",
                    rejection_reason="no_extracted_text",
                    fallback_domain=domain,
                    fallback_bucket_label=planned_bucket,
                )
                continue
            if len(candidate.full_text) < self.MIN_TEXT_LENGTH:
                self._record_candidate_decision(
                    candidate=candidate,
                    result=result,
                    stage=stage,
                    state="extraction_failed",
                    rejection_reason="extracted_text_too_short",
                    fallback_domain=domain,
                    fallback_bucket_label=planned_bucket,
                )
                continue

            relevance_total = 0.5
            relevance_diag: dict[str, object] = {}
            if story_packet:
                semantic_scores = self._score_semantic_candidate(
                    semantic_scorer,
                    candidate,
                )
                semantic_similarity = (
                    semantic_scores.get("aggregate_similarity")
                    if semantic_scores
                    else None
                )
                semantic_chunk_similarity = (
                    semantic_scores.get("chunk_similarity") if semantic_scores else None
                )
                relevance = self._relevance_scorer.score(
                    candidate_title=candidate.title,
                    candidate_text=candidate.full_text,
                    candidate_date=candidate.published_date,
                    story_packet=story_packet,
                    seen_domains=candidate_domains,
                    candidate_domain=candidate.domain,
                    semantic_similarity=semantic_similarity,
                    semantic_chunk_similarity=semantic_chunk_similarity,
                )
                relevance_total = relevance.total
                candidate.relevance_score = relevance.total
                candidate.semantic_similarity = relevance.semantic_similarity
                candidate.semantic_title_similarity = (
                    semantic_scores.get("title_similarity") if semantic_scores else None
                )
                candidate.semantic_lede_similarity = (
                    semantic_scores.get("lede_similarity") if semantic_scores else None
                )
                candidate.semantic_chunk_similarity = semantic_chunk_similarity
                candidate.distinctive_term_overlap = relevance.distinctive_term_overlap
                candidate.direct_evidence_score = relevance.direct_evidence_score
                candidate.coverage_type = relevance.coverage_type
                relevance_diag = relevance.to_diagnostics().model_dump(mode="json")
                if candidate.semantic_title_similarity is not None:
                    relevance_diag["semantic_title_similarity"] = (
                        candidate.semantic_title_similarity
                    )
                if candidate.semantic_lede_similarity is not None:
                    relevance_diag["semantic_lede_similarity"] = (
                        candidate.semantic_lede_similarity
                    )
                if candidate.semantic_chunk_similarity is not None:
                    relevance_diag["semantic_chunk_similarity"] = (
                        candidate.semantic_chunk_similarity
                    )
                if relevance.rejection_reason:
                    logger.debug(
                        "Skipping low-relevance source %s: %s",
                        candidate.url,
                        relevance.rejection_reason,
                    )
                    self._record_candidate_decision(
                        candidate=candidate,
                        result=result,
                        stage=stage,
                        state="relevance_rejected",
                        rejection_reason=relevance.rejection_reason,
                        relevance_diagnostics=relevance_diag,
                        fallback_bucket_label=planned_bucket,
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
                self._record_candidate_decision(
                    candidate=candidate,
                    result=result,
                    stage=stage,
                    state="duplicate_rejected",
                    rejection_reason=dup_result.reason,
                    relevance_diagnostics=relevance_diag,
                    fallback_bucket_label=planned_bucket,
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
                semantic_similarity=candidate.semantic_similarity,
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
            self._record_candidate_decision(
                candidate=candidate,
                result=result,
                stage=stage,
                state="extracted",
                relevance_diagnostics=relevance_diag,
                fallback_bucket_label=planned_bucket,
            )
            candidate_urls.add(normalized_url)
            candidate_domains.add(domain)

        return scored_candidates

    def _build_candidate_semantic_scorer(
        self,
        story_packet: StoryPacket | None,
        description: str,
    ) -> CandidateSemanticScorer | None:
        if not story_packet or not self._semantic_candidate_scoring_enabled():
            return None
        try:
            if self._embedding_provider is None:
                return CandidateSemanticScorer(story_packet, description)
            return CandidateSemanticScorer(
                story_packet,
                description,
                embedding_provider=self._embedding_provider,
            )
        except Exception as exc:
            if not self._semantic_fail_open():
                raise
            logger.warning(
                "Candidate semantic scoring unavailable; continuing deterministic relevance: %s",
                exc,
            )
            return None

    def _score_semantic_candidate(
        self,
        semantic_scorer: CandidateSemanticScorer | None,
        candidate: SourceCandidate,
    ) -> dict[str, float | None] | None:
        if semantic_scorer is None:
            return None
        try:
            if hasattr(semantic_scorer, "score_candidate_diagnostics"):
                scores = semantic_scorer.score_candidate_diagnostics(
                    candidate.title,
                    candidate.full_text,
                )
                return {
                    "aggregate_similarity": scores.aggregate_similarity,
                    "title_similarity": scores.title_similarity,
                    "lede_similarity": scores.lede_similarity,
                    "chunk_similarity": getattr(scores, "chunk_similarity", None),
                }
            return {
                "aggregate_similarity": semantic_scorer.score_candidate(
                    candidate.title,
                    candidate.full_text,
                ),
                "title_similarity": None,
                "lede_similarity": None,
                "chunk_similarity": None,
            }
        except Exception as exc:
            if not self._semantic_fail_open():
                raise
            logger.warning(
                "Candidate semantic similarity failed for %s; continuing: %s",
                candidate.url,
                exc,
            )
            return None

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
            ]
            if (
                missing
                and not pool
                and not self._setting_bool(
                    "allow_same_bias_backfill",
                    False,
                )
            ):
                break
            is_backfill = False
            if not pool:
                pool = remaining
                is_backfill = True

            policy_pool = [
                item
                for item in pool
                if self._candidate_allowed_by_policy(
                    item[1],
                    sources,
                    plan,
                    enforce_result_quota=not is_backfill,
                )
            ]
            if not policy_pool:
                for _score, candidate in pool:
                    self._mark_candidate_decision(
                        candidate.url,
                        state="policy_rejected",
                        rejection_reason="strict_bucket_or_exact_bias_policy",
                    )
                if missing:
                    break
                break
            selected_score, selected = max(
                policy_pool,
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
            self._mark_candidate_decision(selected.url, state="retained")
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
                domain=extract_domain(url),
                title=article.title or "",
                published_date=article.date,
                author=article.author,
                full_text=article.text or "",
                extraction_error=article.error or "No content extracted",
                extraction_error_code=article.error_code,
                extractor_method=article.extractor_method,
                http_status=article.http_status,
                bias_result=None,
                og_image_url=article.og_image_url,
                embedded_post_urls=article.embedded_post_urls,
                image_alt_text=article.image_alt_text,
                media_captions=article.media_captions,
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
            og_image_url=article.og_image_url,
            embedded_post_urls=article.embedded_post_urls,
            image_alt_text=article.image_alt_text,
            media_captions=article.media_captions,
        )

    def _record_primary_decision(
        self,
        candidate: SourceCandidate,
        *,
        state: str,
        rejection_reason: str | None = None,
    ) -> None:
        self._record_candidate_decision(
            candidate=candidate,
            result=SearchResult(
                title=candidate.title,
                url=candidate.url,
                snippet="",
                source=candidate.domain,
            ),
            stage="primary",
            state=state,
            rejection_reason=rejection_reason,
        )

    def _record_candidate_decision(
        self,
        *,
        candidate: SourceCandidate | None,
        result: SearchResult,
        stage: str,
        state: str,
        rejection_reason: str | None = None,
        relevance_diagnostics: dict[str, object] | None = None,
        fallback_domain: str = "",
        fallback_bucket_label: str | None = None,
    ) -> None:
        url = candidate.url if candidate else result.url
        domain = candidate.domain if candidate else fallback_domain
        title = candidate.title if candidate else result.title
        media_diagnostics = {}
        exact_bias = None
        bucket_label = None
        if candidate:
            bucket_label = candidate.bucket_label or fallback_bucket_label
            if not bucket_label and candidate.bias_result:
                bucket_label = self._bucket_label(candidate)
            if not bucket_label:
                bucket_label = self._bucket_label(candidate)
            exact_bias = self._candidate_bias(candidate)
            media_diagnostics = {
                "og_image_url": candidate.og_image_url,
                "embedded_post_urls": list(candidate.embedded_post_urls),
                "image_alt_text_count": len(candidate.image_alt_text),
                "media_caption_count": len(candidate.media_captions),
            }
        relevance_payload = dict(relevance_diagnostics or {})
        rss_diagnostics = self._rss_story_diagnostics_by_url.get(
            self._normalize_url(url)
        )
        if stage == "rss" and rss_diagnostics:
            relevance_payload["rss_story_match"] = rss_diagnostics
        self._candidate_decisions.append(
            CandidateDecision(
                url=url,
                domain=domain,
                title=title,
                stage=stage
                if stage in {"primary", "rss", "site_search", "open_web"}
                else "unknown",
                state=state,
                bucket_label=bucket_label,
                exact_bias=exact_bias,
                rejection_reason=rejection_reason,
                extraction_error=candidate.extraction_error if candidate else None,
                extraction_error_code=(
                    candidate.extraction_error_code if candidate else None
                ),
                extractor_method=candidate.extractor_method if candidate else None,
                http_status=candidate.http_status if candidate else None,
                relevance_score=candidate.relevance_score if candidate else None,
                relevance_diagnostics=relevance_payload,
                source_score=candidate.source_score if candidate else None,
                media_diagnostics=media_diagnostics,
            )
        )

    def _capture_rss_story_diagnostics(self) -> None:
        """Index latest RSS story-match diagnostics by normalized candidate URL."""
        diagnostics = getattr(self._rss_retriever, "last_story_diagnostics", []) or []
        for item in diagnostics:
            url = str(item.get("candidate_url") or "")
            if url:
                self._rss_story_diagnostics_by_url[self._normalize_url(url)] = dict(
                    item
                )

    def _mark_candidate_decision(
        self,
        url: str,
        *,
        state: str,
        rejection_reason: str | None = None,
    ) -> None:
        normalized = self._normalize_url(url)
        for index in range(len(self._candidate_decisions) - 1, -1, -1):
            decision = self._candidate_decisions[index]
            if self._normalize_url(decision.url) != normalized:
                continue
            updated = decision.model_copy(
                update={
                    "state": state,
                    "rejection_reason": rejection_reason
                    if rejection_reason is not None
                    else decision.rejection_reason,
                }
            )
            self._candidate_decisions[index] = updated
            return

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

    def _candidate_allowed_by_policy(
        self,
        candidate: SourceCandidate,
        sources: list[SourceCandidate],
        plan: SourcePlan | None = None,
        *,
        enforce_result_quota: bool = True,
    ) -> bool:
        bucket = self._bucket_label(candidate)
        if plan and enforce_result_quota:
            bucket_spec = self._bucket_spec(plan, bucket)
            if (
                bucket_spec
                and bucket_spec.result_quota >= 0
                and self._bucket_counts(sources).get(bucket, 0)
                >= bucket_spec.result_quota
            ):
                return False

        bias = self._candidate_bias(candidate)
        exact_limit = self._setting_int("max_per_exact_bias", 1)
        if (
            exact_limit >= 0
            and self._exact_bias_counts(sources).get(bias, 0) >= exact_limit
        ):
            return False

        bucket_limit = self._setting_int("max_per_bucket_group", 2)
        return not (
            bucket_limit >= 0
            and self._bucket_counts(sources).get(bucket, 0) >= bucket_limit
        )

    def _exact_bias_counts(self, sources: list[SourceCandidate]) -> dict[int, int]:
        counts: dict[int, int] = {}
        for source in sources:
            bias = self._candidate_bias(source)
            counts[bias] = counts.get(bias, 0) + 1
        return counts

    def _bucket_counts(self, sources: list[SourceCandidate]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for source in sources:
            label = self._bucket_label(source)
            counts[label] = counts.get(label, 0) + 1
        return counts

    @staticmethod
    def _candidate_bias(source: SourceCandidate) -> int:
        if source.bias_result:
            return int(getattr(source.bias_result, "bias", 0))
        return 0

    def _setting_bool(self, name: str, default: bool) -> bool:
        value = self._settings_overrides.get(name, getattr(settings, name, default))
        return value if isinstance(value, bool) else default

    def _semantic_candidate_scoring_enabled(self) -> bool:
        return self._setting_bool("semantic_candidate_scoring_enabled", False)

    def _semantic_fail_open(self) -> bool:
        return self._setting_bool("semantic_fail_open", True)

    @staticmethod
    def _setting_int(name: str, default: int) -> int:
        value = getattr(settings, name, default)
        return value if isinstance(value, int) else default

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
            s.bias_result and getattr(s.bias_result, "bias", 0) <= -1 for s in sources
        )
        has_center = any(
            s.bias_result and getattr(s.bias_result, "bias", 99) == 0 for s in sources
        )
        has_right = any(
            s.bias_result and getattr(s.bias_result, "bias", 0) >= 1 for s in sources
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

    def _format_media_context(self, source: SourceCandidate) -> str:
        details: list[str] = []
        if source.og_image_url:
            details.append(f"OG image: {source.og_image_url}")
        if source.embedded_post_urls:
            details.append(
                "Embedded posts: " + ", ".join(source.embedded_post_urls[:3])
            )
        if source.image_alt_text:
            details.append("Image alt text: " + "; ".join(source.image_alt_text[:3]))
        if source.media_captions:
            details.append("Media captions: " + "; ".join(source.media_captions[:3]))
        return "Media: " + " | ".join(details) if details else "Media: none captured"

    @staticmethod
    def _platform_from_url(url: str) -> str:
        lowered = url.lower()
        if "x.com/" in lowered or "twitter.com/" in lowered:
            return "x"
        if "instagram.com/" in lowered:
            return "instagram"
        if "facebook.com/" in lowered:
            return "facebook"
        if "threads.net/" in lowered:
            return "threads"
        if "tiktok.com/" in lowered:
            return "tiktok"
        if "truthsocial.com/" in lowered:
            return "truthsocial"
        return ""
