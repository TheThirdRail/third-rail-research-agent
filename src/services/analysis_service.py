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
from src.services.report_validator import validate_report_sources
from src.services.source_aggregator_service import SourceAggregatorService

logger = logging.getLogger(__name__)


class AnalysisService:
    """Service for orchestrating story analysis workflows.

    Wraps the CrewAI analysis workflow with proper database
    persistence and error handling.
    """

    def __init__(self) -> None:
        """Initialize analysis service with database session."""
        self._session = get_session()
        self._story_crud = StoryCRUD(self._session)
        self._analysis_crud = AnalysisCRUD(self._session)
        self._source_crud = SourceCRUD(self._session)
        self._source_aggregator = SourceAggregatorService()

    def analyze(
        self,
        description: str,
        url: str | None = None,
    ) -> dict[str, Any]:
        """Run analysis workflow and persist results.

        Args:
            description: Description of the story to analyze.
            url: Optional starting URL for the story.

        Returns:
            Dictionary with story_id, report, and analysis metadata.
        """
        logger.info(f"Starting analysis for: {description[:100]}...")

        # Preflight sources and enforce bias spread
        sources = self._source_aggregator.gather_sources(description, url)
        bias_summary = self._source_aggregator.summarize_bias_spread(sources)
        sources_context = self._source_aggregator.format_sources_context(sources)

        # Create story in database
        story = self._story_crud.create(
            title=description[:100],
            description=description,
        )

        try:
            # Persist sources
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

            # Run the CrewAI analysis workflow with prefetched sources
            result = run_analysis(description, url, prefetched_sources=sources_context)
            report = result.get("report", "")

            # Validate report sources
            validate_report_sources(report, [s.url for s in sources])

            # Update story status
            story.status = "analyzed"
            self._session.commit()

            # Create analysis record
            self._analysis_crud.create(
                story_id=story.id,
                full_report_md=report,
                full_report_json=json.dumps(result),
            )

            logger.info(f"Analysis complete for story {story.id[:8]}")

            return {
                "story_id": story.id,
                "report": report,
                "status": "analyzed",
                "source_count": len(sources),
                "bias_spread_met": bool(bias_summary.get("bias_spread_met")),
                "left_source_count": int(bias_summary.get("left_count", 0)),
                "right_source_count": int(bias_summary.get("right_count", 0)),
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
