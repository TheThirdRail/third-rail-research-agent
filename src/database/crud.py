"""CRUD operations for database models."""

import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import desc
from sqlalchemy.orm import Session

from src.database.models import (
    Analysis,
    Source,
    Story,
    VideoPerformance,
)

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
        opinions_by_side: dict | None = None,
        outline: str = "",
        full_report_md: str = "",
        full_report_json: dict | None = None,
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
        )
        self.db.add(analysis)
        self.db.commit()
        self.db.refresh(analysis)
        return analysis

    def get_by_story(self, story_id: str) -> Analysis | None:
        """Get analysis for a story."""
        return self.db.query(Analysis).filter(Analysis.story_id == story_id).first()


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
