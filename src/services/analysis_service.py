"""Service layer for story analysis.

Encapsulates the analysis workflow, providing a clean interface
for CLI and API consumers, with proper persistence handling.
"""

import json
import logging
from typing import Any

from src.crews import run_analysis
from src.core.exceptions import SourceExtractionError
from src.database import AnalysisCRUD, SourceCRUD, StoryCRUD, get_session
from src.services.report_renderer import ReportRenderer, ReportSections, SourceRecord
from src.services.report_validator import (
    validate_evidence_limits,
    validate_orphaned_citations,
    validate_report_sources,
)
from src.services.source_aggregator_service import SourceAggregatorService
from src.services.story_parser_service import StoryParserService

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
        self._analysis_crud = AnalysisCRUD(self._session)
        self._source_crud = SourceCRUD(self._session)
        self._source_aggregator = SourceAggregatorService()
        self._story_parser = StoryParserService()
        self._report_renderer = ReportRenderer()

    def analyze(
        self,
        description: str,
        url: str | None = None,
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

        # ── Stage 1: Story parsing ──────────────────────────────────
        story_packet = self._story_parser.parse(description, url)
        logger.info(
            "Story parsed: headline=%s, actors=%s, queries=%d",
            story_packet.canonical_headline[:60],
            story_packet.actors,
            len(story_packet.query_pack),
        )

        # ── Stage 2: Source gathering with coverage enforcement ─────
        sources = self._source_aggregator.gather_sources(description, url)
        coverage = self._source_aggregator.summarize_coverage(sources)
        sources_context = self._source_aggregator.format_sources_context(sources)

        logger.info(
            "Sources gathered: retained=%d, probed=%d, coverage_ok=%s, missing=%s",
            coverage["retained_count"],
            coverage["probed_count"],
            coverage["coverage_satisfied"],
            coverage["missing_buckets"],
        )

        # ── Stage 3: Create story in database ───────────────────────
        story = self._story_crud.create(
            title=description[:100],
            description=description,
        )

        # Persist parsed metadata
        story.parsed_metadata = json.dumps(story_packet.model_dump())
        self._session.commit()

        try:
            # ── Stage 4: Persist sources ────────────────────────────
            for src in sources:
                bias = src.bias_result
                self._source_crud.create(
                    story_id=story.id,
                    domain=src.domain,
                    url=src.url,
                    title=src.title,
                    full_text=src.full_text,
                    author=src.author,
                    published_date=src.published_date,
                    political_bias=getattr(bias, "bias", 0) if bias else 0,
                    bias_confidence=getattr(bias, "confidence", 0.0) if bias else 0.0,
                    bias_method=getattr(bias, "method", "unknown") if bias else "unknown",
                )

            # ── Stage 5: Run CrewAI analysis ────────────────────────
            result = run_analysis(description, url, prefetched_sources=sources_context)
            crew_report = result.get("report", "")

            # ── Stage 6: Validate ───────────────────────────────────
            allowed_urls = [s.url for s in sources]
            try:
                validate_report_sources(crew_report, allowed_urls)
            except SourceExtractionError as val_err:
                logger.warning("Report validation issue: %s", val_err)

            evidence_warnings = validate_evidence_limits(
                crew_report, coverage.get("missing_buckets", [])
            )
            citation_warnings = validate_orphaned_citations(crew_report)
            all_warnings = evidence_warnings + citation_warnings
            if all_warnings:
                logger.warning("Report warnings: %s", "; ".join(all_warnings))

                        # ── Stage 7: Deterministic rendering ────────────────────
            source_records = [
                SourceRecord(
                    source_id=f"S{i+1}",
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
                )
                for i, src in enumerate(sources)
            ]
            # Build sections from the crew report (pass-through for now;
            # full structured output_pydantic will replace this once model
            # lock-in is resolved)
            sections = ReportSections(
                executive_summary=crew_report,
            )
            report = self._report_renderer.render(
                sources=source_records,
                sections=sections,
                missing_buckets=coverage.get("missing_buckets", []),
            )

            # ── Stage 8: Persist analysis ───────────────────────────
            story.status = "analyzed"
            self._session.commit()

            self._analysis_crud.create(
                story_id=story.id,
                full_report_md=report,
                full_report_json=json.dumps(result),
            )

            logger.info("Analysis complete for story %s", story.id[:8])

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
                "warnings": all_warnings,
            }
        except SourceExtractionError:
            story.status = "failed"
            self._session.commit()
            raise
        except Exception:
            story.status = "failed"
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
