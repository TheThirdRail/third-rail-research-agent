"""Service layer for story analysis.

Encapsulates the analysis workflow, providing a clean interface
for CLI and API consumers, with proper persistence handling.
"""

import logging
from types import TracebackType
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
from src.services.analysis_handoff_builder import AnalysisHandoffBuilder
from src.services.analysis_persistence_builder import (
    AnalysisPersistenceBuilder,
    url_key,
)
from src.services.report_renderer import ReportRenderer, SourceRecord
from src.services.report_validator import (
    validate_evidence_limits,
    validate_orphaned_citations,
    validate_report_sources,
    validate_structured_section_payload,
)
from src.services.semantic_analysis_indexer import SemanticAnalysisIndexer
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
        self._handoff_builder = AnalysisHandoffBuilder()
        self._semantic_indexer = SemanticAnalysisIndexer(
            self._session,
            semantic_memory_cls=SemanticMemoryService,
        )
        self._closed = False

    def close(self) -> None:
        """Close the service database session once."""
        if self._closed:
            return
        self._session.close()
        self._closed = True

    def __enter__(self) -> "AnalysisService":
        """Return this service for context-managed use."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the service session without handling transaction state."""
        self.close()

    def analyze(
        self,
        description: str,
        url: str | None = None,
        options: AnalysisOptions | None = None,
    ) -> dict[str, Any]:
        """Run analysis workflow and persist results.

        Pipeline stages:
        1. Seed URL extraction and story parsing (deterministic headline → StoryPacket)
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

        # ── Stage 1: Extract seed context and parse story before retrieval ─
        seed_context = source_aggregator.prepare_seed_context(url)
        seed_source = seed_context.primary if seed_context else None
        rss_hint = seed_context.rss_hint if seed_context else None
        story_packet = story_parser.parse(
            description,
            url,
            rss_title=rss_hint.title if rss_hint else None,
            rss_summary=rss_hint.summary if rss_hint else None,
            seed_title=seed_source.title if seed_source else None,
            seed_text=seed_source.full_text if seed_source else None,
        )
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
                seed_context=seed_context,
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
                summary=self._handoff_builder.retrieval_summary(coverage),
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
                decision = retained_decisions.get(url_key(src.url))
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
                summary=self._handoff_builder.pre_crew_summary(
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
                url_key(candidate.url): source.id
                for candidate, source in persisted_sources
            }
            self._source_finding_crud.bulk_create(
                story_id=story.id,
                analysis_id=analysis.id,
                findings=structured_sections.source_findings,
                source_ids_by_ref=source_ids_by_ref,
            )
            self._attach_semantic_memory_analysis(
                story_id=story.id,
                analysis_id=analysis.id,
                options_snapshot=options_snapshot,
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
            agent_finding_specs = self._handoff_builder.agent_finding_specs(
                structured_sections,
                coverage,
            )
            self._agent_finding_crud.bulk_create(
                story_id=story.id,
                analysis_id=analysis.id,
                findings=agent_finding_specs,
            )
            for handoff in self._handoff_builder.agent_handoffs_from_findings(
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
                finding_specs=agent_finding_specs,
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
        return self._semantic_indexer.index_retrieval_context(
            story_id=story_id,
            story_packet=story_packet,
            description=description,
            sources=sources,
            visual_bundle=visual_bundle,
            options_snapshot=options_snapshot,
        )

    def _attach_semantic_memory_analysis(
        self,
        *,
        story_id: str,
        analysis_id: str,
        options_snapshot: dict[str, Any] | None = None,
    ) -> None:
        self._semantic_indexer.attach_analysis(
            story_id=story_id,
            analysis_id=analysis_id,
            options_snapshot=options_snapshot,
        )

    def _build_semantic_agent_contexts(
        self,
        *,
        story_id: str,
        description: str,
        sources: list[tuple[Any, Source]],
        options_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        return self._semantic_indexer.build_agent_contexts(
            story_id=story_id,
            description=description,
            sources=sources,
            options_snapshot=options_snapshot,
        )

    def _index_semantic_analysis_findings(
        self,
        *,
        story_id: str,
        analysis_id: str,
        finding_specs: list[dict[str, Any]],
        options_snapshot: dict[str, Any] | None = None,
    ) -> None:
        self._semantic_indexer.index_analysis_findings(
            story_id=story_id,
            analysis_id=analysis_id,
            finding_specs=finding_specs,
            options_snapshot=options_snapshot,
        )

    def _agent_finding_specs(
        self,
        sections: AnalysisReportSections,
        coverage: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return self._handoff_builder.agent_finding_specs(sections, coverage)

    @staticmethod
    def _agent_handoffs_from_findings(
        finding_specs: list[dict[str, Any]],
        coverage: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return AnalysisHandoffBuilder().agent_handoffs_from_findings(
            finding_specs,
            coverage,
        )

    @staticmethod
    def _retrieval_handoff_summary(coverage: dict[str, Any]) -> str:
        return AnalysisHandoffBuilder().retrieval_summary(coverage)

    @staticmethod
    def _pre_crew_handoff_summary(
        coverage: dict[str, Any],
        semantic_agent_contexts: dict[str, str],
        visual_bundle: VisualEvidenceBundle,
    ) -> str:
        return AnalysisHandoffBuilder().pre_crew_summary(
            coverage,
            semantic_agent_contexts,
            visual_bundle,
        )

    @staticmethod
    def _compact_summary(text: str, max_chars: int = 280) -> str:
        return AnalysisHandoffBuilder.compact_summary(text, max_chars)

    @staticmethod
    def _join_section_parts(parts: list[tuple[str, object]]) -> str:
        return AnalysisHandoffBuilder.join_section_parts(parts)

    @staticmethod
    def _source_refs_from_text(text: str) -> list[str]:
        return AnalysisHandoffBuilder.source_refs_from_text(text)

    @staticmethod
    def _coverage_snapshot(coverage: dict[str, Any]) -> str:
        return AnalysisHandoffBuilder().coverage_snapshot(coverage)

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
            preferred = (
                ["center"] if getattr(settings, "exact_center_preferred", True) else []
            )
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
            "embedding_model": str(
                option_or_setting("embedding_model", "fake-hash-v1")
            ),
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
            "strict_bucket_enforcement": options_snapshot["strict_bucket_enforcement"],
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
        return SemanticAnalysisIndexer.semantic_bias_bucket(bias_score)

    @staticmethod
    def _url_key(url: str) -> str:
        return url_key(url)

    @staticmethod
    def _json_loads(raw: str | None) -> Any:
        return AnalysisPersistenceBuilder.json_loads(raw)

    @staticmethod
    def _analysis_run_payload(run: AnalysisRun | None) -> dict[str, Any] | None:
        return AnalysisPersistenceBuilder().analysis_run_payload(run)

    @staticmethod
    def _retrieval_candidate_payload(
        candidate: RetrievalCandidate,
    ) -> dict[str, Any]:
        return AnalysisPersistenceBuilder().retrieval_candidate_payload(candidate)

    @staticmethod
    def _retained_decisions_by_url(
        decisions: list[CandidateDecision],
    ) -> dict[str, CandidateDecision]:
        return {
            url_key(decision.url): decision
            for decision in decisions
            if decision.state == "retained"
        }
