"""Narrative analyzer service.

Sits after fact extraction and rhetorical analysis, before
report writing. Produces structured narrative patterns and
profile-aware creator angles.
"""

from __future__ import annotations

import logging

from src.schemas.narrative import NarrativeResult, OpinionCluster

logger = logging.getLogger(__name__)


class NarrativeAnalyzerService:
    """Build structured narrative analysis from fact/rhetoric findings.

    This is a data-assembly stage that organizes upstream outputs
    into the NarrativeResult schema. The CrewAI narrative_analyzer
    agent does the actual analytical work; this service validates
    and structures the output.
    """

    def build_from_crew_output(
        self,
        crew_narrative_raw: dict[str, object],
        missing_buckets: list[str] | None = None,
    ) -> NarrativeResult:
        """Build NarrativeResult from raw crew output dict.

        Args:
            crew_narrative_raw: Raw dict from the narrative analysis task.
            missing_buckets: Bias buckets that were not filled.

        Returns:
            Validated NarrativeResult.
        """
        missing = missing_buckets or []

        opinion_clusters_raw = crew_narrative_raw.get("opinion_clusters", [])
        opinion_clusters = (
            opinion_clusters_raw if isinstance(opinion_clusters_raw, list) else []
        )

        result = NarrativeResult(
            mainstream_narrative=self._string(
                crew_narrative_raw.get("mainstream_narrative")
            ),
            alternative_narrative=self._string(
                crew_narrative_raw.get("alternative_narrative")
            ),
            profile_aware_creator_angles=self._string_list(
                crew_narrative_raw.get("creator_angles")
            ),
            omission_patterns_by_side=self._string_list_dict(
                crew_narrative_raw.get("omission_patterns")
            ),
            headline_framing_diffs=self._string_list(
                crew_narrative_raw.get("headline_diffs")
            ),
            opinion_clusters=[
                OpinionCluster(**c) for c in opinion_clusters if isinstance(c, dict)
            ],
            evidence_confidence=self._assess_confidence(missing),
            missing_perspectives=missing,
        )

        logger.info(
            "Narrative analysis: mainstream=%d chars, alt=%d chars, "
            "angles=%d, missing=%s",
            len(result.mainstream_narrative),
            len(result.alternative_narrative),
            len(result.profile_aware_creator_angles),
            missing or "none",
        )

        return result

    @staticmethod
    def _assess_confidence(missing_buckets: list[str]) -> str:
        """Assess overall evidence confidence based on coverage gaps."""
        if not missing_buckets:
            return "high"
        if len(missing_buckets) == 1:
            return "moderate"
        return "low"

    @staticmethod
    def _string(value: object) -> str:
        return value if isinstance(value, str) else ""

    @staticmethod
    def _string_list(value: object) -> list[str]:
        return [str(item) for item in value] if isinstance(value, list) else []

    @staticmethod
    def _string_list_dict(value: object) -> dict[str, list[str]]:
        if not isinstance(value, dict):
            return {}
        output: dict[str, list[str]] = {}
        for key, items in value.items():
            output[str(key)] = (
                [str(item) for item in items] if isinstance(items, list) else []
            )
        return output
