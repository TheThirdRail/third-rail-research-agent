"""Persistence payload helpers for analysis diagnostics."""

import json
from typing import Any

from src.database.models import AnalysisRun, RetrievalCandidate


class AnalysisPersistenceBuilder:
    """Build stable JSON-compatible payloads from persisted analysis rows."""

    @staticmethod
    def json_loads(raw: str | None) -> Any:
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def analysis_run_payload(self, run: AnalysisRun | None) -> dict[str, Any] | None:
        if not run:
            return None
        return {
            "id": run.id,
            "status": run.status,
            "options_snapshot": self.json_loads(run.options_snapshot_json),
            "coverage_snapshot": self.json_loads(run.coverage_snapshot_json),
            "candidate_census": self.json_loads(run.candidate_census_json),
            "report_validation_warnings": self.json_loads(
                run.report_validation_warnings_json
            ),
            "error": run.error,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }

    def retrieval_candidate_payload(
        self,
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
            "relevance_diagnostics": self.json_loads(
                candidate.relevance_diagnostics_json
            ),
            "source_score": candidate.source_score,
            "media_diagnostics": self.json_loads(candidate.media_diagnostics_json),
            "discovered_at": candidate.discovered_at.isoformat()
            if candidate.discovered_at
            else None,
        }


def url_key(url: str) -> str:
    """Normalize source URLs for retained-decision and source-id lookups."""
    return (url or "").strip().rstrip("/").lower()
