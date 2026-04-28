"""SQLAlchemy database models for Research Agent."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class Story(Base):
    """A news story that can be analyzed."""

    __tablename__ = "stories"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    keywords: Mapped[str] = mapped_column(Text, default="")  # JSON array as string
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    performance_prediction: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, selected, analyzed, published

    # Relationships
    sources: Mapped[list["Source"]] = relationship(
        back_populates="story", cascade="all, delete-orphan"
    )
    analysis: Mapped["Analysis | None"] = relationship(
        back_populates="story", uselist=False, cascade="all, delete-orphan"
    )
    performance: Mapped["VideoPerformance | None"] = relationship(
        back_populates="story", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Story(id={self.id[:8]}, title='{self.title[:50]}...')>"


class Source(Base):
    """A news source covering a story."""

    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    story_id: Mapped[str] = mapped_column(String(36), ForeignKey("stories.id"))
    domain: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    full_text: Mapped[str] = mapped_column(Text, default="")
    political_bias: Mapped[int] = mapped_column(Integer, default=0)  # -4 to +4
    bias_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    bias_method: Mapped[str] = mapped_column(
        String(50), default="unknown"
    )  # dataset, llm, manual
    factual_rating: Mapped[str | None] = mapped_column(String(50), nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    story: Mapped["Story"] = relationship(back_populates="sources")

    def __repr__(self) -> str:
        return f"<Source(domain={self.domain}, bias={self.political_bias})>"


class Analysis(Base):
    """Analysis results for a story."""

    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    story_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stories.id"), unique=True
    )

    # Facts
    agreed_facts: Mapped[str] = mapped_column(Text, default="[]")  # JSON array
    left_only_facts: Mapped[str] = mapped_column(Text, default="[]")  # JSON array
    right_only_facts: Mapped[str] = mapped_column(Text, default="[]")  # JSON array

    # Narratives
    mainstream_narrative: Mapped[str] = mapped_column(Text, default="")
    alternative_takes: Mapped[str] = mapped_column(Text, default="")
    libertarian_angle: Mapped[str] = mapped_column(Text, default="")

    # Opinions
    opinions_by_side: Mapped[str] = mapped_column(Text, default="{}")  # JSON object

    # Output
    outline: Mapped[str] = mapped_column(Text, default="")
    full_report_md: Mapped[str] = mapped_column(Text, default="")
    full_report_json: Mapped[str] = mapped_column(Text, default="{}")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    story: Mapped["Story"] = relationship(back_populates="analysis")

    def __repr__(self) -> str:
        return f"<Analysis(story_id={self.story_id[:8]})>"


class VideoPerformance(Base):
    """YouTube performance data for a published story."""

    __tablename__ = "video_performance"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    story_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stories.id"), unique=True
    )
    youtube_video_id: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Metrics
    views_day_1: Mapped[int] = mapped_column(Integer, default=0)
    views_week_1: Mapped[int] = mapped_column(Integer, default=0)
    views_total: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    retention_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    ctr_percent: Mapped[float | None] = mapped_column(Float, nullable=True)

    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    story: Mapped["Story"] = relationship(back_populates="performance")

    def __repr__(self) -> str:
        return f"<VideoPerformance(views={self.views_total}, likes={self.likes})>"


class ChannelProfile(Base):
    """Channel configuration and preferences."""

    __tablename__ = "channel_profiles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    worldview: Mapped[str] = mapped_column(String(100), default="libertarian")
    topics: Mapped[str] = mapped_column(Text, default="[]")  # JSON array
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<ChannelProfile(name={self.name})>"


class DailySpend(Base):
    """Track daily LLM spending for budget enforcement."""

    __tablename__ = "daily_spend"

    date: Mapped[datetime] = mapped_column(
        DateTime, primary_key=True, default=datetime.utcnow
    )
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    budget_limit: Mapped[float] = mapped_column(Float, default=0.0)  # 0.0 = free only

    def __repr__(self) -> str:
        return f"<DailySpend(date={self.date.date()}, amount={self.amount:.4f}, limit={self.budget_limit})>"


class AgentConfiguration(Base):
    """Configuration for a specific agent."""

    __tablename__ = "agent_configurations"

    agent_name: Mapped[str] = mapped_column(String(50), primary_key=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    budget_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    free_tier: Mapped[bool] = mapped_column(Boolean, default=False)
    reasoning_effort: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<AgentConfiguration(name={self.agent_name}, model={self.model})>"
