"""Service layer for story analysis.

Encapsulates the analysis workflow, providing a clean interface
for CLI and API consumers, with proper persistence handling.
"""

import json
import logging
import re
from typing import Any

from src.core import analysis_events
from src.core.config import settings
from src.core.embedding_provider import get_embedding_provider
from src.core.exceptions import SourceExtractionError
from src.crews import run_analysis
from src.database import (
    AgentFindingCRUD,
    AgentHandoffCRUD,
    AnalysisCRUD,
    AnalysisRunCRUD,
    RetrievalCandidateCRUD,
    SourceCRUD,
    SourceFindingCRUD,
    StoryCRUD,
    VisualEvidenceRecordCRUD,
    get_session,
)
from src.database.models import AgentHandoff, AnalysisRun, RetrievalCandidate, Source
from src.schemas.analysis_options import AnalysisOptions
from src.schemas.analysis_report_sections import AnalysisReportSections
from src.schemas.retrieval_diagnostics import CandidateDecision
from src.schemas.visual_evidence import VisualEvidenceBundle
from src.services.report_renderer import ReportRenderer, SourceRecord
from src.services.report_validator import (
    validate_evidence_limits,
    validate_orphaned_citations,
    validate_report_sources,
    validate_structured_section_payload,
)
from src.services.semantic_memory_service import SemanticMemoryService
from src.services.source_aggregator_service import SourceAggregatorService
from src.services.story_parser_service import StoryParserService
from src.services.visual_evidence_service import VisualEvidenceService

logger = logging.getLogger(__name__)


class AnalysisService:
    """Service for orchestrating story analysis workflows.

    Wraps the CrewAI analysis workflow with proper database
    persistence and error handling.
    """

    def __init__(self) -> None:
        """Initialize analysis service with database session and pipeline services."""
        self._session = get_session()
        self._story_crud = StoryCRUD(self._session)
        self._agent_finding_crud = AgentFindingCRUD(self._session)
        self._agent_handoff_crud = AgentHandoffCRUD(self._session)
        self._analysis_crud = AnalysisCRUD(self._session)
        self._analysis_run_crud = AnalysisRunCRUD(self._session)
        self._retrieval_candidate_crud = RetrievalCandidateCRUD(self._session)
        self._source_finding_crud = SourceFindingCRUD(self._session)
        self._visual_evidence_record_crud = VisualEvidenceRecordCRUD(self._session)
        self._source_crud = SourceCRUD(self._session)
        self._source_aggregator = SourceAggregatorService()
        self._story_parser = StoryParserService()
        self._report_renderer = ReportRenderer()
        self._visual_evidence = VisualEvidenceService()

    def analyze(
        self,
        description: str,
        url: str | None = None,
        options: AnalysisOptions | None = None,
    ) -> dict[str, Any]:
        """Run analysis workflow and persist results.

        Pipeline stages:
        1. Story parsing (deterministic headline → StoryPacket)
        2. Source gathering with coverage enforcement
        3. CrewAI analysis (facts, rhetoric, narrative)
        4. Report validation & deterministic rendering
        5. Database persistence

        Args:
            description: Description of the story to analyze.
            url: Optional starting URL for the story.

        Returns:
            Dictionary with story_id, report, and analysis metadata.
        """
        logger.info("Starting analysis for: %s...", description[:100])
        _run_start = analysis_events.run_started(
            story_id="pending",
            description=description,
            url=url,
        )

        options_snapshot = self._analysis_options_snapshot(options)
        source_aggregator = SourceAggregatorService(
            settings_overrides=self._source_aggregator_overrides(options_snapshot),
            embedding_provider=get_embedding_provider(
                options_snapshot["embedding_provider"],
                options_snapshot["embedding_model"],
            ),
        )
        story_parser = StoryParserService(
            semantic_query_expansion_enabled=options_snapshot[
                "enable_semantic_query_expansion"
            ],
        )

        # ── Stage 1: Story parsing ──────────────────────────────────
        story_packet = story_parser.parse(description, url)
        logger.info(
            "Story parsed: headline=%s, actors=%s, queries=%d",
            story_packet.canonical_headline[:60],
            story_packet.actors,
            len(story_packet.query_pack),
        )

        # ── Stage 2: Create story/run before retrieval ──────────────
        story = self._story_crud.create(
            title=description[:100],
            description=description,
        )
        story.parsed_metadata = story_packet.model_dump_json()
        self._session.commit()
        analysis_run = self._analysis_run_crud.create(
            story.id,
            options_snapshot=options_snapshot,
        )

        coverage: dict[str, Any] = {}
        sources: list[Any] = []
        retrieval_candidates_persisted = False
        try:
            # ── Stage 3: Source gathering with coverage enforcement ─
            sources = source_aggregator.gather_sources(
                description,
                url,
                story_packet=story_packet,
            )
            coverage = source_aggregator.summarize_coverage(sources)
            sources_context = source_aggregator.format_sources_context(sources)
            if not options_snapshot["enable_visual_evidence_resolution"]:
                visual_bundle = VisualEvidenceBundle()
            else:
                visual_evidence = self._visual_evidence
                if options and options.enable_screenshot_capture is not None:
                    visual_evidence = VisualEvidenceService(
                        screenshot_capture_enabled=options_snapshot[
                            "enable_screenshot_capture"
                        ]
                    )
                visual_bundle = visual_evidence.analyze(
                    source_aggregator.collect_media_pointers(sources)
                )
            visual_context = visual_bundle.to_context_block()

            logger.info(
                "Sources gathered: retained=%d, probed=%d, coverage_ok=%s, missing=%s",
                coverage["retained_count"],
                coverage["probed_count"],
                coverage["coverage_satisfied"],
                coverage["missing_buckets"],
            )
            analysis_events.bucket_fill_ratio(
                story_id="pending",
                coverage=coverage,
            )

            candidate_census = source_aggregator.candidate_census(
                missing_buckets=coverage.get("missing_buckets", [])
            )
            analysis_events.candidate_totals(
                story_id=story.id,
                candidate_decisions=source_aggregator.candidate_decisions,
            )
            analysis_events.bucket_fill_ratio(
                story_id=story.id,
                coverage=coverage,
            )
            # Bucket probe events from lane attempts
            for attempt in candidate_census.bucket_lane_attempts:
                analysis_events.bucket_probe_started(
                    story_id=story.id,
                    bucket_label=attempt.bucket_label,
                    stage=attempt.stage,
                    exact_bias=attempt.exact_bias,
                    query=attempt.query,
                    domains=attempt.domains,
                )
            # RSS precision
            rss_decisions = [
                d
                for d in source_aggregator.candidate_decisions
                if getattr(d, "stage", "") == "rss"
            ]
            rss_accepted = sum(
                1 for d in rss_decisions if getattr(d, "state", "") == "retained"
            )
            analysis_events.rss_precision_at_accept(
                story_id=story.id,
                rss_candidates=len(rss_decisions),
                rss_accepted=rss_accepted,
            )
            # Visual/social post events
            visual_total = len(visual_bundle.records)
            visual_success = sum(
                1 for r in visual_bundle.records if not r.fallback_reason
            )
            visual_fallback = sum(1 for r in visual_bundle.records if r.fallback_reason)
            analysis_events.social_post_resolve_result(
                story_id=story.id,
                total=visual_total,
                success=visual_success,
                fallback=visual_fallback,
            )
            self._retrieval_candidate_crud.bulk_create(
                analysis_run_id=analysis_run.id,
                story_id=story.id,
                decisions=source_aggregator.candidate_decisions,
            )
            retrieval_candidates_persisted = True
            self._analysis_run_crud.complete(
                analysis_run.id,
                status="retrieval_complete",
                coverage_snapshot=coverage,
                candidate_census=candidate_census.model_dump(mode="json"),
            )
            self._agent_handoff_crud.create(
                story_id=story.id,
                stage="post_retrieval",
                from_agent="source_aggregator",
                to_agent="analysis_crew",
                summary=self._retrieval_handoff_summary(coverage),
                payload={
                    "coverage": coverage,
                    "candidate_census": candidate_census.model_dump(mode="json"),
                    "source_count": len(sources),
                    "visual_evidence_count": len(visual_bundle.records),
                },
            )
            # ── Stage 4: Persist sources ────────────────────────────
            persisted_sources: list[tuple[Any, Source]] = []
            retained_decisions = self._retained_decisions_by_url(
                source_aggregator.candidate_decisions
            )
            for src in sources:
                bias = src.bias_result
                decision = retained_decisions.get(self._url_key(src.url))
                source = self._source_crud.create(
                    story_id=story.id,
                    domain=src.domain,
                    url=src.url,
                    title=src.title,
                    full_text=src.full_text,
                    author=src.author,
                    published_date=src.published_date,
                    political_bias=getattr(bias, "bias", 0) if bias else 0,
                    bias_confidence=getattr(bias, "confidence", 0.0) if bias else 0.0,
                    bias_method=getattr(bias, "method", "unknown")
                    if bias
                    else "unknown",
                    relevance_score=src.relevance_score,
                    source_score=src.source_score,
                    bucket_label=src.bucket_label
                    or (decision.bucket_label if decision else None),
                    exact_bias=(
                        getattr(bias, "bias", None)
                        if bias
                        else (decision.exact_bias if decision else None)
                    ),
                    coverage_type=src.coverage_type,
                    extractor_method=src.extractor_method,
                    extraction_error=src.extraction_error,
                    extraction_error_code=src.extraction_error_code,
                    http_status=src.http_status,
                    og_image_url=src.og_image_url,
                    embedded_post_urls=src.embedded_post_urls,
                    image_alt_text=src.image_alt_text,
                    media_captions=src.media_captions,
                    relevance_diagnostics=decision.relevance_diagnostics
                    if decision
                    else {},
                    media_diagnostics=decision.media_diagnostics if decision else {},
                )
                persisted_sources.append((src, source))

            semantic_indexed = self._index_semantic_memory(
                story_id=story.id,
                story_packet=story_packet,
                description=description,
                sources=persisted_sources,
                visual_bundle=visual_bundle,
                options_snapshot=options_snapshot,
            )
            semantic_agent_contexts = (
                self._build_semantic_agent_contexts(
                    story_id=story.id,
                    description=description,
                    sources=persisted_sources,
                    options_snapshot=options_snapshot,
                )
                if semantic_indexed
                else {}
            )

            # ── Stage 5: Run CrewAI analysis ────────────────────────
            analysis_kwargs = {
                "prefetched_sources": sources_context,
                "visual_evidence_context": visual_context,
            }
            if semantic_agent_contexts:
                analysis_kwargs["agent_contexts"] = semantic_agent_contexts
            self._agent_handoff_crud.create(
                story_id=story.id,
                stage="pre_crew",
                from_agent="analysis_service",
                to_agent="analysis_crew",
                summary=self._pre_crew_handoff_summary(
                    coverage,
                    semantic_agent_contexts,
                    visual_bundle,
                ),
                payload={
                    "semantic_context_agents": sorted(semantic_agent_contexts),
                    "visual_evidence_count": len(visual_bundle.records),
                    "visual_limitations": visual_bundle.limitations,
                    "source_refs": [
                        {
                            "source_ref": f"S{index}",
                            "source_id": source.id,
                            "url": source.url,
                            "domain": source.domain,
                        }
                        for index, (_candidate, source) in enumerate(
                            persisted_sources, 1
                        )
                    ],
                },
            )
            result = run_analysis(description, url, **analysis_kwargs)
            crew_report = result.get("report", "")
            structured_sections = AnalysisReportSections.from_crew_payload(
                result,
                fallback_summary=description,
            )
            if not structured_sections.coverage_snapshot:
                structured_sections.coverage_snapshot = self._coverage_snapshot(
                    coverage
                )

            # ── Stage 6: Validate structured crew output ─────────────
            allowed_urls = [s.url for s in sources]
            citation_warnings = validate_orphaned_citations(crew_report)
            all_warnings = citation_warnings
            if all_warnings:
                logger.warning("Report warnings: %s", "; ".join(all_warnings))

            # ── Stage 7: Deterministic rendering ────────────────────
            source_records = [
                SourceRecord(
                    source_id=f"S{i + 1}",
                    title=src.title,
                    domain=src.domain,
                    url=src.url,
                    bias=getattr(src.bias_result, "bias", 0) if src.bias_result else 0,
                    bias_label=(
                        getattr(src.bias_result, "bias_label", "Unknown")
                        if src.bias_result
                        else "Unknown"
                    ),
                    confidence=(
                        getattr(src.bias_result, "confidence", 0.0)
                        if src.bias_result
                        else 0.0
                    ),
                    key_framing=self._source_finding_value(
                        structured_sections,
                        f"S{i + 1}",
                        "key_framing",
                    ),
                    notable_claim=self._source_finding_value(
                        structured_sections,
                        f"S{i + 1}",
                        "notable_claim",
                    ),
                )
                for i, src in enumerate(sources)
            ]
            # Repair missing source findings with deterministic fallbacks
            self._report_renderer.repair_source_findings(source_records)
            # Validate source findings completeness
            from src.services.report_validator import validate_source_findings

            finding_warnings = validate_source_findings(
                structured_sections.source_findings,
                retained_source_count=len(source_records),
            )
            all_warnings.extend(finding_warnings)

            sections = structured_sections.to_renderer_sections()
            sections.evidence_limitations.extend(visual_bundle.limitations)
            validate_structured_section_payload(sections)
            report = self._report_renderer.render(
                sources=source_records,
                sections=sections,
                missing_buckets=coverage.get("missing_buckets", []),
            )
            validate_report_sources(report, allowed_urls)
            evidence_warnings = validate_evidence_limits(
                report, coverage.get("missing_buckets", [])
            )
            all_warnings.extend(evidence_warnings)

            # Observability: source matrix key framing gaps
            missing_key_framing = sum(1 for sr in source_records if not sr.key_framing)
            analysis_events.source_matrix_missing_key_framing(
                story_id=story.id,
                total_sources=len(source_records),
                missing_count=missing_key_framing,
            )
            analysis_events.report_validation_warnings(
                story_id=story.id,
                warnings=all_warnings,
            )

            # ── Stage 8: Persist analysis ───────────────────────────
            story.status = "analyzed"
            self._session.commit()

            analysis = self._analysis_crud.create(
                story_id=story.id,
                full_report_md=report,
                full_report_json=result,
                coverage_snapshot_json=coverage,
                candidate_census_json=candidate_census.model_dump(mode="json"),
                visual_evidence_json=visual_bundle.model_dump(mode="json"),
                report_validation_warnings_json=all_warnings,
            )
            source_ids_by_ref = {
                f"S{index}": source.id
                for index, (_candidate, source) in enumerate(persisted_sources, 1)
            }
            source_ids_by_url = {
                self._url_key(candidate.url): source.id
                for candidate, source in persisted_sources
            }
            self._source_finding_crud.bulk_create(
                story_id=story.id,
                analysis_id=analysis.id,
                findings=structured_sections.source_findings,
                source_ids_by_ref=source_ids_by_ref,
            )
            for source_ref, source_id in source_ids_by_ref.items():
                key_framing = self._source_finding_value(
                    structured_sections,
                    source_ref,
                    "key_framing",
                )
                if key_framing:
                    self._source_crud.update_key_framing(source_id, key_framing)
            self._visual_evidence_record_crud.bulk_create(
                story_id=story.id,
                analysis_id=analysis.id,
                records=visual_bundle.records,
                source_ids_by_url=source_ids_by_url,
            )
            self._agent_handoff_crud.attach_analysis(story.id, analysis.id)
            agent_finding_specs = self._agent_finding_specs(
                structured_sections,
                coverage,
            )
            self._agent_finding_crud.bulk_create(
                story_id=story.id,
                analysis_id=analysis.id,
                findings=agent_finding_specs,
            )
            for handoff in self._agent_handoffs_from_findings(
                agent_finding_specs,
                coverage,
            ):
                self._agent_handoff_crud.create(
                    story_id=story.id,
                    analysis_id=analysis.id,
                    **handoff,
                )
            self._index_semantic_analysis_findings(
                story_id=story.id,
                analysis_id=analysis.id,
                sections=structured_sections,
                coverage=coverage,
                options_snapshot=options_snapshot,
            )
            self._analysis_run_crud.complete(
                analysis_run.id,
                status="retrieval_complete",
                coverage_snapshot=coverage,
                candidate_census=candidate_census.model_dump(mode="json"),
                report_validation_warnings=all_warnings,
            )

            logger.info("Analysis complete for story %s", story.id[:8])
            analysis_events.run_completed(
                story_id=story.id,
                status="analyzed",
                start_time=_run_start,
                source_count=len(sources),
                warnings_count=len(all_warnings),
            )

            return {
                "story_id": story.id,
                "report": report,
                "status": "analyzed",
                "source_count": len(sources),
                "coverage_satisfied": bool(coverage.get("coverage_satisfied")),
                "missing_buckets": coverage.get("missing_buckets", []),
                "left_source_count": int(coverage.get("left_count", 0)),
                "center_source_count": int(coverage.get("center_count", 0)),
                "right_source_count": int(coverage.get("right_count", 0)),
                "probed_count": int(coverage.get("probed_count", 0)),
                "candidate_census": candidate_census.model_dump(mode="json"),
                "warnings": all_warnings,
                "visual_evidence_count": len(visual_bundle.records),
                "analysis_options": options_snapshot,
            }
        except SourceExtractionError:
            story.status = "failed"
            if not coverage:
                coverage = source_aggregator.summarize_coverage([])
            candidate_census = source_aggregator.candidate_census(
                missing_buckets=coverage.get("missing_buckets", [])
            )
            if not retrieval_candidates_persisted:
                self._retrieval_candidate_crud.bulk_create(
                    analysis_run_id=analysis_run.id,
                    story_id=story.id,
                    decisions=source_aggregator.candidate_decisions,
                )
            self._analysis_run_crud.complete(
                analysis_run.id,
                status="failed",
                coverage_snapshot=coverage,
                candidate_census=candidate_census.model_dump(mode="json"),
                error="source_extraction_error",
            )
            self._session.commit()
            raise
        except Exception:
            story.status = "failed"
            if not coverage:
                coverage = source_aggregator.summarize_coverage([])
            candidate_census = source_aggregator.candidate_census(
                missing_buckets=coverage.get("missing_buckets", [])
            )
            if not retrieval_candidates_persisted:
                self._retrieval_candidate_crud.bulk_create(
                    analysis_run_id=analysis_run.id,
                    story_id=story.id,
                    decisions=source_aggregator.candidate_decisions,
                )
            self._analysis_run_crud.complete(
                analysis_run.id,
                status="failed",
                coverage_snapshot=coverage,
                candidate_census=candidate_census.model_dump(mode="json"),
                error="analysis_error",
            )
            self._session.commit()
            raise

    def get_analysis(self, story_id: str) -> dict[str, Any] | None:
        """Retrieve existing analysis for a story.

        Args:
            story_id: ID of the story to retrieve analysis for.

        Returns:
            Analysis data or None if not found.
        """
        story = self._story_crud.get_by_id(story_id)
        if not story or not story.analysis:
            return None

        return {
            "story_id": story.id,
            "title": story.title,
            "report": story.analysis.full_report_md,
            "created_at": story.analysis.created_at.isoformat(),
        }

    def get_diagnostics(self, story_id: str) -> dict[str, Any] | None:
        """Retrieve persisted retrieval/coverage diagnostics for a story."""
        story = self._story_crud.get_by_id(story_id)
        if not story:
            return None

        analysis = story.analysis
        latest_run = (
            self._session.query(AnalysisRun)
            .filter(AnalysisRun.story_id == story_id)
            .order_by(AnalysisRun.started_at.desc())
            .first()
        )
        candidates = (
            self._session.query(RetrievalCandidate)
            .filter(RetrievalCandidate.story_id == story_id)
            .order_by(RetrievalCandidate.created_at.asc())
            .all()
        )
        analysis_run_payload = self._analysis_run_payload(latest_run)
        run_coverage = (
            analysis_run_payload.get("coverage_snapshot", {})
            if analysis_run_payload
            else {}
        )
        run_census = (
            analysis_run_payload.get("candidate_census", {})
            if analysis_run_payload
            else {}
        )
        parsed_metadata = self._json_loads(story.parsed_metadata or "{}")
        return {
            "story_id": story_id,
            "analysis_id": analysis.id if analysis else None,
            "analysis_run": analysis_run_payload,
            "query_expansion_diagnostics": parsed_metadata.get(
                "query_expansion_diagnostics",
                {},
            ),
            "coverage": self._json_loads(
                analysis.coverage_snapshot_json if analysis else "{}"
            )
            or run_coverage,
            "candidate_census": self._json_loads(
                analysis.candidate_census_json if analysis else "{}"
            )
            or run_census,
            "visual_evidence": self._json_loads(
                analysis.visual_evidence_json if analysis else "{}"
            ),
            "report_validation_warnings": self._json_loads(
                analysis.report_validation_warnings_json if analysis else "[]"
            )
            or (
                analysis_run_payload.get("report_validation_warnings", [])
                if analysis_run_payload
                else []
            ),
            "agent_handoff_snapshot": self._json_loads(
                analysis.agent_handoff_snapshot_json if analysis else "{}"
            ),
            "retrieval_candidates": [
                self._retrieval_candidate_payload(candidate) for candidate in candidates
            ],
        }

    def get_handoff(self, story_id: str, stage: str) -> dict[str, Any] | None:
        """Retrieve a persisted agent handoff bundle by stage."""
        story = self._story_crud.get_by_id(story_id)
        if not story:
            return None
        handoff = (
            self._session.query(AgentHandoff)
            .filter(AgentHandoff.story_id == story_id)
            .filter(AgentHandoff.stage == stage)
            .order_by(AgentHandoff.created_at.desc())
            .first()
        )
        if not handoff:
            return None
        return {
            "story_id": story_id,
            "analysis_id": handoff.analysis_id,
            "stage": handoff.stage,
            "from_agent": handoff.from_agent,
            "to_agent": handoff.to_agent,
            "summary": handoff.summary,
            "payload": self._json_loads(handoff.payload_json),
            "created_at": handoff.created_at.isoformat(),
        }

    def _index_semantic_memory(
        self,
        *,
        story_id: str,
        story_packet,
        description: str,
        sources: list[tuple[Any, Source]],
        visual_bundle: VisualEvidenceBundle,
        options_snapshot: dict[str, Any] | None = None,
    ) -> bool:
        options_snapshot = options_snapshot or {}
        if not options_snapshot.get(
            "enable_semantic_memory",
            getattr(settings, "semantic_memory_enabled", False),
        ):
            return False
        try:
            semantic_memory = SemanticMemoryService(
                self._session,
                embedding_provider=get_embedding_provider(
                    options_snapshot.get("embedding_provider"),
                    options_snapshot.get("embedding_model"),
                ),
                vector_store_backend=options_snapshot.get("vector_store"),
            )
            semantic_memory.index_seed_story(
                story_id,
                story_packet,
                description,
                {"stage": "analysis_service"},
            )
            for index, (candidate, source) in enumerate(sources, 1):
                bias = getattr(candidate, "bias_result", None)
                bias_score = source.political_bias
                semantic_memory.index_source_article(
                    story_id=story_id,
                    source_id=source.id,
                    title=source.title,
                    text=source.full_text,
                    metadata={
                        "stage": "analysis_service",
                        "domain": source.domain,
                        "url": source.url,
                        "source_ref": f"S{index}",
                        "bias_score": bias_score,
                        "bias_label": (
                            getattr(bias, "bias_label", None) if bias else None
                        ),
                        "bias_bucket": self._semantic_bias_bucket(bias_score),
                        "coverage_type": getattr(candidate, "coverage_type", None),
                    },
                )
            source_lookup = {
                self._url_key(candidate.url): (source.id, f"S{index}")
                for index, (candidate, source) in enumerate(sources, 1)
            }
            for index, record in enumerate(visual_bundle.records, 1):
                source_id, source_ref = source_lookup.get(
                    self._url_key(record.source_url),
                    (None, None),
                )
                semantic_memory.index_visual_evidence(
                    story_id=story_id,
                    source_id=source_id,
                    record=record,
                    metadata={
                        "stage": "analysis_service",
                        "visual_ref": f"V{index}",
                        "source_ref": source_ref,
                    },
                )
            doc_count = 1 + len(sources) + len(visual_bundle.records)
            analysis_events.semantic_memory_chunks_total(
                story_id=story_id,
                chunks=doc_count,
                documents=doc_count,
            )
            logger.info(
                "Semantic memory indexed for story %s: retained_sources=%d visual_records=%d",
                story_id[:8],
                len(sources),
                len(visual_bundle.records),
            )
            return True
        except Exception as exc:
            logger.warning(
                "Semantic memory indexing failed for story %s; continuing: %s",
                story_id[:8],
                exc,
            )
            return False

    def _build_semantic_agent_contexts(
        self,
        *,
        story_id: str,
        description: str,
        sources: list[tuple[Any, Source]],
        options_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        try:
            options_snapshot = options_snapshot or {}
            source_refs = {
                source.id: f"S{index}"
                for index, (_candidate, source) in enumerate(sources, 1)
            }
            semantic_memory = SemanticMemoryService(
                self._session,
                embedding_provider=get_embedding_provider(
                    options_snapshot.get("embedding_provider"),
                    options_snapshot.get("embedding_model"),
                ),
                vector_store_backend=options_snapshot.get("vector_store"),
            )
            contexts = semantic_memory.build_agent_contexts(
                story_id,
                description,
                source_refs=source_refs,
            )
            logger.info(
                "Semantic agent contexts built for story %s: agents=%s",
                story_id[:8],
                ",".join(sorted(contexts)),
            )
            return contexts
        except Exception as exc:
            logger.warning(
                "Semantic agent context retrieval failed for story %s; continuing: %s",
                story_id[:8],
                exc,
            )
            return {}

    def _index_semantic_analysis_findings(
        self,
        *,
        story_id: str,
        analysis_id: str,
        sections: AnalysisReportSections,
        coverage: dict[str, Any],
        options_snapshot: dict[str, Any] | None = None,
    ) -> None:
        options_snapshot = options_snapshot or {}
        if not options_snapshot.get(
            "enable_semantic_memory",
            getattr(settings, "semantic_memory_enabled", False),
        ):
            return
        try:
            semantic_memory = SemanticMemoryService(
                self._session,
                embedding_provider=get_embedding_provider(
                    options_snapshot.get("embedding_provider"),
                    options_snapshot.get("embedding_model"),
                ),
                vector_store_backend=options_snapshot.get("vector_store"),
            )
            indexed = 0
            for spec in self._agent_finding_specs(sections, coverage):
                semantic_memory.index_structured_finding(
                    story_id=story_id,
                    analysis_id=analysis_id,
                    agent_name=spec["agent_name"],
                    document_type=spec["document_type"],
                    finding_type=spec["finding_type"],
                    finding_text=spec["text"],
                    metadata={
                        "stage": "analysis_service",
                        "section_fields": spec["section_fields"],
                        "source_refs": spec["source_refs"],
                    },
                )
                indexed += 1
            logger.info(
                "Semantic analysis findings indexed for story %s: documents=%d",
                story_id[:8],
                indexed,
            )
        except Exception as exc:
            logger.warning(
                "Semantic analysis finding indexing failed for story %s; continuing: %s",
                story_id[:8],
                exc,
            )

    def _agent_finding_specs(
        self,
        sections: AnalysisReportSections,
        coverage: dict[str, Any],
    ) -> list[dict[str, Any]]:
        specs = [
            {
                "agent_name": "fact_extractor",
                "document_type": "fact_claims",
                "finding_type": "fact_claims",
                "section_fields": [
                    "what_happened",
                    "directly_observable",
                    "agreed_facts",
                    "what_is_disputed",
                ],
                "text": self._join_section_parts(
                    [
                        ("What happened", sections.what_happened),
                        ("Directly observable", sections.directly_observable),
                        ("Agreed facts", sections.agreed_facts),
                        ("What is disputed", sections.what_is_disputed),
                    ]
                ),
            },
            {
                "agent_name": "rhetorical_analyst",
                "document_type": "rhetoric_findings",
                "finding_type": "rhetoric_findings",
                "section_fields": [
                    "framing_omissions",
                    "logical_fallacies",
                    "linguistic_manipulation",
                    "fact_opinion_ambiguities",
                ],
                "text": self._join_section_parts(
                    [
                        ("Framing omissions", sections.framing_omissions),
                        ("Logical fallacies", sections.logical_fallacies),
                        (
                            "Linguistic manipulation",
                            sections.linguistic_manipulation,
                        ),
                        (
                            "Fact-opinion ambiguities",
                            sections.fact_opinion_ambiguities,
                        ),
                    ]
                ),
            },
            {
                "agent_name": "narrative_analyzer",
                "document_type": "narrative_findings",
                "finding_type": "narrative_findings",
                "section_fields": [
                    "mainstream_narrative",
                    "alternative_takes",
                    "creator_angles",
                    "recommended_approach",
                    "video_outline",
                ],
                "text": self._join_section_parts(
                    [
                        ("Mainstream narrative", sections.mainstream_narrative),
                        ("Alternative takes", sections.alternative_takes),
                        ("Creator angles", sections.creator_angles),
                        ("Recommended approach", sections.recommended_approach),
                        ("Video outline", sections.video_outline),
                    ]
                ),
            },
            {
                "agent_name": "narrative_analyzer",
                "document_type": "coverage_asymmetry",
                "finding_type": "coverage_asymmetry",
                "section_fields": ["coverage_snapshot", "evidence_limitations"],
                "text": self._join_section_parts(
                    [
                        ("Coverage snapshot", sections.coverage_snapshot),
                        ("Evidence limitations", sections.evidence_limitations),
                        (
                            "Coverage diagnostics",
                            json.dumps(coverage, sort_keys=True),
                        ),
                    ]
                ),
            },
        ]
        durable_specs = []
        for spec in specs:
            if not spec["text"].strip():
                continue
            source_refs = self._source_refs_from_text(spec["text"])
            durable_specs.append(
                {
                    **spec,
                    "source_refs": source_refs,
                    "metadata": {
                        "document_type": spec["document_type"],
                        "section_fields": spec["section_fields"],
                    },
                }
            )
        return durable_specs

    @staticmethod
    def _agent_handoffs_from_findings(
        finding_specs: list[dict[str, Any]],
        coverage: dict[str, Any],
    ) -> list[dict[str, Any]]:
        stage_by_agent = {
            "fact_extractor": "fact_handoff",
            "rhetorical_analyst": "rhetoric_handoff",
            "narrative_analyzer": "narrative_handoff",
        }
        handoffs = []
        for spec in finding_specs:
            agent_name = spec["agent_name"]
            stage = stage_by_agent.get(agent_name, "report_handoff")
            handoffs.append(
                {
                    "stage": stage,
                    "from_agent": agent_name,
                    "to_agent": "report_writer",
                    "summary": AnalysisService._compact_summary(spec["text"]),
                    "payload": {
                        "finding_type": spec["finding_type"],
                        "document_type": spec["document_type"],
                        "section_fields": spec["section_fields"],
                        "source_refs": spec["source_refs"],
                        "coverage_satisfied": bool(coverage.get("coverage_satisfied")),
                    },
                }
            )
        return handoffs

    @staticmethod
    def _retrieval_handoff_summary(coverage: dict[str, Any]) -> str:
        missing = coverage.get("missing_buckets") or []
        missing_text = ", ".join(missing) if missing else "none"
        return (
            f"Retrieved {coverage.get('retained_count', 0)} sources after probing "
            f"{coverage.get('probed_count', 0)} candidates; missing buckets: "
            f"{missing_text}."
        )

    @staticmethod
    def _pre_crew_handoff_summary(
        coverage: dict[str, Any],
        semantic_agent_contexts: dict[str, str],
        visual_bundle: VisualEvidenceBundle,
    ) -> str:
        return (
            f"Prepared crew context for {coverage.get('retained_count', 0)} sources, "
            f"{len(semantic_agent_contexts)} semantic context lanes, and "
            f"{len(visual_bundle.records)} visual evidence records."
        )

    @staticmethod
    def _compact_summary(text: str, max_chars: int = 280) -> str:
        compact = re.sub(r"\s+", " ", text or "").strip()
        if len(compact) <= max_chars:
            return compact
        return compact[:max_chars].rstrip() + "..."

    @staticmethod
    def _join_section_parts(parts: list[tuple[str, object]]) -> str:
        lines: list[str] = []
        for label, value in parts:
            if isinstance(value, list):
                text = "\n".join(f"- {item}" for item in value if str(item).strip())
            else:
                text = str(value or "").strip()
            if text:
                lines.append(f"{label}:\n{text}")
        return "\n\n".join(lines)

    @staticmethod
    def _source_refs_from_text(text: str) -> list[str]:
        refs = sorted(
            set(re.findall(r"\bS\d+\b", text or "")),
            key=lambda ref: int(ref[1:]),
        )
        return refs

    @staticmethod
    def _coverage_snapshot(coverage: dict[str, Any]) -> str:
        exact_counts = coverage.get("exact_bias_counts") or {}
        exact_parts = [
            f"{bias:+d}: {count}"
            for bias, count in sorted(
                exact_counts.items(), key=lambda item: int(item[0])
            )
        ]
        missing = coverage.get("missing_buckets") or []
        missing_text = ", ".join(missing) if missing else "none"
        exact_text = ", ".join(exact_parts) if exact_parts else "unavailable"
        return (
            f"Retained {coverage.get('retained_count', 0)} sources after probing "
            f"{coverage.get('probed_count', 0)} candidates. "
            f"Grouped counts: left={coverage.get('left_count', 0)}, "
            f"center={coverage.get('center_count', 0)}, "
            f"right={coverage.get('right_count', 0)}. "
            f"Exact-bias counts: {exact_text}. Missing required buckets: {missing_text}."
        )

    @staticmethod
    def _analysis_options_snapshot(options: AnalysisOptions | None) -> dict[str, Any]:
        option_values = options.model_dump(exclude_none=True) if options else {}

        def option_or_setting(name: str, default: Any = None) -> Any:
            return option_values.get(name, getattr(settings, name, default))

        required = option_values.get("required_bucket_groups")
        if required is None:
            required = AnalysisService._split_csv_setting(
                getattr(settings, "required_bucket_groups", "left_side,right_side")
            )
        else:
            required = AnalysisService._split_csv_setting(required)
        preferred = option_values.get("preferred_bucket_groups")
        if preferred is None:
            preferred = ["center"] if getattr(settings, "exact_center_preferred", True) else []
        else:
            preferred = AnalysisService._split_csv_setting(preferred)

        return {
            "strict_bucket_enforcement": bool(
                option_or_setting("strict_bucket_enforcement", True)
            ),
            "required_bucket_groups": list(required or []),
            "preferred_bucket_groups": list(preferred or []),
            "enable_semantic_memory": bool(
                option_values.get(
                    "enable_semantic_memory",
                    getattr(settings, "semantic_memory_enabled", False),
                )
            ),
            "enable_semantic_candidate_scoring": bool(
                option_values.get(
                    "enable_semantic_candidate_scoring",
                    getattr(settings, "semantic_candidate_scoring_enabled", False),
                )
            ),
            "enable_semantic_query_expansion": bool(
                option_values.get(
                    "enable_semantic_query_expansion",
                    getattr(settings, "semantic_query_expansion_enabled", False),
                )
            ),
            "enable_visual_evidence_resolution": bool(
                option_or_setting("enable_visual_evidence_resolution", True)
            ),
            "enable_screenshot_capture": bool(
                option_values.get(
                    "enable_screenshot_capture",
                    getattr(settings, "screenshot_capture_enabled", False),
                )
            ),
            "embedding_provider": str(option_or_setting("embedding_provider", "fake")),
            "embedding_model": str(option_or_setting("embedding_model", "fake-hash-v1")),
            "vector_store": str(
                option_values.get(
                    "vector_store",
                    getattr(settings, "semantic_vector_store", "none"),
                )
            ),
        }

    @staticmethod
    def _source_aggregator_overrides(
        options_snapshot: dict[str, Any],
    ) -> dict[str, object]:
        return {
            "strict_bucket_enforcement": options_snapshot[
                "strict_bucket_enforcement"
            ],
            "required_bucket_groups": ",".join(
                options_snapshot["required_bucket_groups"]
            ),
            "semantic_candidate_scoring_enabled": options_snapshot[
                "enable_semantic_candidate_scoring"
            ],
        }

    @staticmethod
    def _split_csv_setting(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if not isinstance(value, str):
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    @staticmethod
    def _source_finding_value(
        sections: AnalysisReportSections,
        source_id: str,
        field_name: str,
    ) -> str:
        for finding in sections.source_findings:
            if finding.source_id.strip().upper() == source_id.upper():
                return str(getattr(finding, field_name, "") or "").strip()
        return ""

    @staticmethod
    def _semantic_bias_bucket(bias_score: int) -> str:
        if bias_score <= -1:
            return "left_side"
        if bias_score >= 1:
            return "right_side"
        return "center"

    @staticmethod
    def _url_key(url: str) -> str:
        return (url or "").strip().rstrip("/").lower()

    @staticmethod
    def _json_loads(raw: str | None) -> Any:
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    @classmethod
    def _analysis_run_payload(cls, run: AnalysisRun | None) -> dict[str, Any] | None:
        if not run:
            return None
        return {
            "id": run.id,
            "status": run.status,
            "options_snapshot": cls._json_loads(run.options_snapshot_json),
            "coverage_snapshot": cls._json_loads(run.coverage_snapshot_json),
            "candidate_census": cls._json_loads(run.candidate_census_json),
            "report_validation_warnings": cls._json_loads(
                run.report_validation_warnings_json
            ),
            "error": run.error,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }

    @classmethod
    def _retrieval_candidate_payload(
        cls,
        candidate: RetrievalCandidate,
    ) -> dict[str, Any]:
        return {
            "id": candidate.id,
            "analysis_run_id": candidate.analysis_run_id,
            "url": candidate.url,
            "domain": candidate.domain,
            "title": candidate.title,
            "stage": candidate.stage,
            "state": candidate.state,
            "bucket_label": candidate.bucket_label,
            "exact_bias": candidate.exact_bias,
            "rejection_reason": candidate.rejection_reason,
            "extraction_error": candidate.extraction_error,
            "extraction_error_code": candidate.extraction_error_code,
            "extractor_method": candidate.extractor_method,
            "http_status": candidate.http_status,
            "relevance_score": candidate.relevance_score,
            "relevance_diagnostics": cls._json_loads(
                candidate.relevance_diagnostics_json
            ),
            "source_score": candidate.source_score,
            "media_diagnostics": cls._json_loads(candidate.media_diagnostics_json),
            "discovered_at": candidate.discovered_at.isoformat()
            if candidate.discovered_at
            else None,
        }

    @staticmethod
    def _retained_decisions_by_url(
        decisions: list[CandidateDecision],
    ) -> dict[str, CandidateDecision]:
        return {
            AnalysisService._url_key(decision.url): decision
            for decision in decisions
            if decision.state == "retained"
        }
