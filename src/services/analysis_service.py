"""Service layer for story analysis.

Encapsulates the analysis workflow, providing a clean interface
for CLI and API consumers, with proper persistence handling.
"""

import json
import logging
from typing import Any

from src.crews import run_analysis
from src.database import AnalysisCRUD, StoryCRUD, get_session

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

        # Run the CrewAI analysis workflow
        result = run_analysis(description, url)
        report = result.get("report", "")

        # Create or find story in database
        story = self._story_crud.create(
            title=description[:100],
            description=description,
        )

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
        }

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
