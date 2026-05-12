"""CRUD operations for database models."""

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import desc
from sqlalchemy.orm import Session

from src.core.time_utils import utc_now_naive
from src.database.models import (
    AgentFinding,
    AgentHandoff,
    Analysis,
    AnalysisRun,
    RetrievalCandidate,
    Source,
    SourceFindingRecord,
    Story,
    VideoPerformance,
    VisualEvidenceRecordModel,
)
from src.schemas.analysis_report_sections import SourceFinding
from src.schemas.retrieval_diagnostics import CandidateDecision
from src.schemas.visual_evidence import VisualEvidenceRecord

# --- Story CRUD ---


class StoryCRUD:
    """CRUD operations for Story model."""

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        title: str,
        description: str = "",
        keywords: list[str] | None = None,
        relevance_score: float = 0.0,
    ) -> Story:
        """Create a new story."""
        story = Story(
            id=str(uuid4()),
            title=title,
            description=description,
            keywords=json.dumps(keywords or []),
            relevance_score=relevance_score,
        )
        self.db.add(story)
        self.db.commit()
        self.db.refresh(story)
        return story

    def get_by_id(self, story_id: str) -> Story | None:
        """Get story by ID."""
        return self.db.query(Story).filter(Story.id == story_id).first()

    def list_recent(self, limit: int = 10, status: str | None = None) -> list[Story]:
        """List recent stories, optionally filtered by status."""
        query = self.db.query(Story)
        if status:
            query = query.filter(Story.status == status)
        return query.order_by(desc(Story.discovered_at)).limit(limit).all()

    def update_status(self, story_id: str, status: str) -> Story | None:
        """Update story status."""
        story = self.get_by_id(story_id)
        if story:
            story.status = status
            self.db.commit()
            self.db.refresh(story)
        return story

    def delete(self, story_id: str) -> bool:
        """Delete story by ID."""
        story = self.get_by_id(story_id)
        if story:
            self.db.delete(story)
            self.db.commit()
            return True
        return False


# --- Source CRUD ---


class SourceCRUD:
    """CRUD operations for Source model."""

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        story_id: str,
        domain: str,
        url: str,
        title: str,
        full_text: str = "",
        author: str | None = None,
        published_date: datetime | None = None,
        political_bias: int = 0,
        bias_confidence: float = 0.0,
        bias_method: str = "unknown",
        relevance_score: float | None = None,
        source_score: float | None = None,
        bucket_label: str | None = None,
        exact_bias: int | None = None,
        coverage_type: str | None = None,
        extractor_method: str | None = None,
        extraction_error: str | None = None,
        extraction_error_code: str | None = None,
        http_status: int | None = None,
        og_image_url: str | None = None,
        embedded_post_urls: list[str] | tuple[str, ...] | None = None,
        image_alt_text: list[str] | tuple[str, ...] | None = None,
        media_captions: list[str] | tuple[str, ...] | None = None,
        relevance_diagnostics: dict[str, Any] | None = None,
        media_diagnostics: dict[str, Any] | None = None,
    ) -> Source:
        """Create a new source."""
        source = Source(
            id=str(uuid4()),
            story_id=story_id,
            domain=domain,
            url=url,
            title=title,
            full_text=full_text,
            author=author,
            published_date=published_date,
            political_bias=political_bias,
            bias_confidence=bias_confidence,
            bias_method=bias_method,
            relevance_score=relevance_score,
            source_score=source_score,
            bucket_label=bucket_label,
            exact_bias=exact_bias,
            coverage_type=coverage_type,
            extractor_method=extractor_method,
            extraction_error=extraction_error,
            extraction_error_code=extraction_error_code,
            http_status=http_status,
            og_image_url=og_image_url,
            embedded_post_urls_json=json.dumps(list(embedded_post_urls or [])),
            image_alt_text_json=json.dumps(list(image_alt_text or [])),
            media_captions_json=json.dumps(list(media_captions or [])),
            relevance_diagnostics_json=json.dumps(relevance_diagnostics or {}),
            media_diagnostics_json=json.dumps(media_diagnostics or {}),
        )
        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)
        return source

    def get_by_story(self, story_id: str) -> list[Source]:
        """Get all sources for a story."""
        return self.db.query(Source).filter(Source.story_id == story_id).all()

    def get_by_domain(self, domain: str) -> list[Source]:
        """Get all sources from a domain."""
        return self.db.query(Source).filter(Source.domain == domain).all()

    def update_key_framing(
        self,
        source_id: str,
        key_framing: str,
    ) -> Source | None:
        """Store source-matrix framing on the source row."""
        source = self.db.query(Source).filter(Source.id == source_id).first()
        if not source:
            return None
        source.key_framing = key_framing
        self.db.commit()
        self.db.refresh(source)
        return source


# --- Analysis CRUD ---


class AnalysisCRUD:
    """CRUD operations for Analysis model."""

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        story_id: str,
        agreed_facts: list[str] | None = None,
        left_only_facts: list[str] | None = None,
        right_only_facts: list[str] | None = None,
        mainstream_narrative: str = "",
        alternative_takes: str = "",
        libertarian_angle: str = "",
        opinions_by_side: dict[str, Any] | None = None,
        outline: str = "",
        full_report_md: str = "",
        full_report_json: dict[str, Any] | None = None,
        coverage_snapshot_json: dict[str, Any] | None = None,
        candidate_census_json: dict[str, Any] | None = None,
        visual_evidence_json: dict[str, Any] | None = None,
        report_validation_warnings_json: list[str] | None = None,
        agent_handoff_snapshot_json: dict[str, Any] | None = None,
    ) -> Analysis:
        """Create analysis for a story."""
        analysis = Analysis(
            id=str(uuid4()),
            story_id=story_id,
            agreed_facts=json.dumps(agreed_facts or []),
            left_only_facts=json.dumps(left_only_facts or []),
            right_only_facts=json.dumps(right_only_facts or []),
            mainstream_narrative=mainstream_narrative,
            alternative_takes=alternative_takes,
            libertarian_angle=libertarian_angle,
            opinions_by_side=json.dumps(opinions_by_side or {}),
            outline=outline,
            full_report_md=full_report_md,
            full_report_json=json.dumps(full_report_json or {}),
            coverage_snapshot_json=json.dumps(coverage_snapshot_json or {}),
            candidate_census_json=json.dumps(candidate_census_json or {}),
            visual_evidence_json=json.dumps(visual_evidence_json or {}),
            report_validation_warnings_json=json.dumps(
                report_validation_warnings_json or []
            ),
            agent_handoff_snapshot_json=json.dumps(agent_handoff_snapshot_json or {}),
        )
        self.db.add(analysis)
        self.db.commit()
        self.db.refresh(analysis)
        return analysis

    def get_by_story(self, story_id: str) -> Analysis | None:
        """Get analysis for a story."""
        return self.db.query(Analysis).filter(Analysis.story_id == story_id).first()


class AnalysisRunCRUD:
    """CRUD operations for analysis run diagnostics."""

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        story_id: str,
        status: str = "running",
        options_snapshot: dict[str, Any] | None = None,
    ) -> AnalysisRun:
        run = AnalysisRun(
            id=str(uuid4()),
            story_id=story_id,
            status=status,
            options_snapshot_json=json.dumps(options_snapshot or {}),
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def complete(
        self,
        run_id: str,
        *,
        status: str,
        coverage_snapshot: dict[str, Any] | None = None,
        candidate_census: dict[str, Any] | None = None,
        report_validation_warnings: list[str] | None = None,
        error: str | None = None,
    ) -> AnalysisRun | None:
        run = self.db.query(AnalysisRun).filter(AnalysisRun.id == run_id).first()
        if not run:
            return None
        run.status = status
        run.coverage_snapshot_json = json.dumps(coverage_snapshot or {})
        run.candidate_census_json = json.dumps(candidate_census or {})
        if report_validation_warnings is not None:
            run.report_validation_warnings_json = json.dumps(report_validation_warnings)
        run.error = error
        run.completed_at = utc_now_naive()
        self.db.commit()
        self.db.refresh(run)
        return run


class RetrievalCandidateCRUD:
    """CRUD operations for retrieval candidate diagnostics."""

    def __init__(self, db: Session):
        self.db = db

    def bulk_create(
        self,
        *,
        analysis_run_id: str,
        story_id: str,
        decisions: list[CandidateDecision],
    ) -> list[RetrievalCandidate]:
        rows = [
            RetrievalCandidate(
                id=str(uuid4()),
                analysis_run_id=analysis_run_id,
                story_id=story_id,
                url=decision.url,
                domain=decision.domain,
                title=decision.title,
                stage=decision.stage,
                state=decision.state,
                bucket_label=decision.bucket_label,
                exact_bias=decision.exact_bias,
                rejection_reason=decision.rejection_reason,
                extraction_error=decision.extraction_error,
                extraction_error_code=decision.extraction_error_code,
                extractor_method=decision.extractor_method,
                http_status=decision.http_status,
                relevance_score=decision.relevance_score,
                relevance_diagnostics_json=json.dumps(decision.relevance_diagnostics),
                source_score=decision.source_score,
                media_diagnostics_json=json.dumps(decision.media_diagnostics),
                discovered_at=decision.discovered_at,
            )
            for decision in decisions
        ]
        self.db.add_all(rows)
        self.db.commit()
        return rows


class SourceFindingCRUD:
    """CRUD operations for durable source findings."""

    def __init__(self, db: Session):
        self.db = db

    def bulk_create(
        self,
        *,
        story_id: str,
        analysis_id: str,
        findings: list[SourceFinding],
        source_ids_by_ref: dict[str, str],
    ) -> list[SourceFindingRecord]:
        rows = []
        for finding in findings:
            source_ref = finding.source_id.strip().upper()
            row = SourceFindingRecord(
                id=str(uuid4()),
                story_id=story_id,
                analysis_id=analysis_id,
                source_id=source_ids_by_ref.get(source_ref),
                source_ref=source_ref,
                key_framing=finding.key_framing,
                notable_claim=finding.notable_claim,
                evidence_snippet=finding.evidence_snippet,
                confidence=finding.confidence,
                metadata_json=json.dumps(finding.model_dump(mode="json")),
            )
            rows.append(row)
        self.db.add_all(rows)
        self.db.commit()
        return rows


class VisualEvidenceRecordCRUD:
    """CRUD operations for durable visual evidence records."""

    def __init__(self, db: Session):
        self.db = db

    def bulk_create(
        self,
        *,
        story_id: str,
        analysis_id: str,
        records: list[VisualEvidenceRecord],
        source_ids_by_url: dict[str, str],
    ) -> list[VisualEvidenceRecordModel]:
        rows = [
            VisualEvidenceRecordModel(
                id=str(uuid4()),
                story_id=story_id,
                analysis_id=analysis_id,
                source_id=source_ids_by_url.get(self._url_key(record.source_url)),
                source_url=record.source_url,
                media_url=record.media_url,
                media_type=record.media_type,
                platform=record.platform,
                observable_text=record.observable_text,
                visible_symbols_or_numbers_json=json.dumps(
                    record.visible_symbols_or_numbers
                ),
                observable_objects_json=json.dumps(record.observable_objects),
                reported_context=record.reported_context,
                interpretation=record.interpretation,
                legal_characterization=record.legal_characterization,
                confidence=record.confidence,
                metadata_json=json.dumps(record.model_dump(mode="json")),
            )
            for record in records
        ]
        self.db.add_all(rows)
        self.db.commit()
        return rows

    @staticmethod
    def _url_key(url: str) -> str:
        return (url or "").strip().rstrip("/").lower()


class AgentFindingCRUD:
    """CRUD operations for durable agent findings."""

    def __init__(self, db: Session):
        self.db = db

    def bulk_create(
        self,
        *,
        story_id: str,
        analysis_id: str,
        findings: list[dict[str, Any]],
    ) -> list[AgentFinding]:
        rows = [
            AgentFinding(
                id=str(uuid4()),
                story_id=story_id,
                analysis_id=analysis_id,
                agent_name=str(finding.get("agent_name") or ""),
                finding_type=str(finding.get("finding_type") or ""),
                finding_text=str(finding.get("text") or ""),
                source_refs_json=json.dumps(finding.get("source_refs") or []),
                metadata_json=json.dumps(finding.get("metadata") or {}),
            )
            for finding in findings
            if str(finding.get("text") or "").strip()
        ]
        self.db.add_all(rows)
        self.db.commit()
        return rows


class AgentHandoffCRUD:
    """CRUD operations for durable agent handoff bundles."""

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        story_id: str,
        stage: str,
        from_agent: str = "",
        to_agent: str = "",
        summary: str = "",
        payload: dict[str, Any] | None = None,
        analysis_id: str | None = None,
    ) -> AgentHandoff:
        handoff = AgentHandoff(
            id=str(uuid4()),
            story_id=story_id,
            analysis_id=analysis_id,
            stage=stage,
            from_agent=from_agent,
            to_agent=to_agent,
            summary=summary,
            payload_json=json.dumps(payload or {}),
        )
        self.db.add(handoff)
        self.db.commit()
        self.db.refresh(handoff)
        return handoff

    def attach_analysis(self, story_id: str, analysis_id: str) -> int:
        rows = (
            self.db.query(AgentHandoff)
            .filter(AgentHandoff.story_id == story_id)
            .filter(AgentHandoff.analysis_id.is_(None))
            .all()
        )
        for row in rows:
            row.analysis_id = analysis_id
        self.db.commit()
        return len(rows)


# --- VideoPerformance CRUD ---


class PerformanceCRUD:
    """CRUD operations for VideoPerformance model."""

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        story_id: str,
        youtube_video_id: str | None = None,
        views_day_1: int = 0,
        views_week_1: int = 0,
        views_total: int = 0,
        likes: int = 0,
        comments: int = 0,
        retention_percent: float | None = None,
        ctr_percent: float | None = None,
    ) -> VideoPerformance:
        """Create performance data for a story."""
        perf = VideoPerformance(
            id=str(uuid4()),
            story_id=story_id,
            youtube_video_id=youtube_video_id,
            views_day_1=views_day_1,
            views_week_1=views_week_1,
            views_total=views_total,
            likes=likes,
            comments=comments,
            retention_percent=retention_percent,
            ctr_percent=ctr_percent,
        )
        self.db.add(perf)
        self.db.commit()
        self.db.refresh(perf)
        return perf

    def get_by_story(self, story_id: str) -> VideoPerformance | None:
        """Get performance for a story."""
        return (
            self.db.query(VideoPerformance)
            .filter(VideoPerformance.story_id == story_id)
            .first()
        )

    def update(
        self,
        story_id: str,
        views_total: int | None = None,
        likes: int | None = None,
        comments: int | None = None,
    ) -> VideoPerformance | None:
        """Update performance metrics."""
        perf = self.get_by_story(story_id)
        if perf:
            if views_total is not None:
                perf.views_total = views_total
            if likes is not None:
                perf.likes = likes
            if comments is not None:
                perf.comments = comments
            self.db.commit()
            self.db.refresh(perf)
        return perf
