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

from src.core.time_utils import utc_now_naive


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
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    performance_prediction: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, selected, analyzed, published
    parsed_metadata: Mapped[str] = mapped_column(
        Text, default="{}"
    )  # JSON: StoryPacket from story parser

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
    semantic_documents: Mapped[list["SemanticDocument"]] = relationship(
        back_populates="story", cascade="all, delete-orphan"
    )
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(
        back_populates="story", cascade="all, delete-orphan"
    )
    agent_findings: Mapped[list["AgentFinding"]] = relationship(
        back_populates="story", cascade="all, delete-orphan"
    )
    agent_handoffs: Mapped[list["AgentHandoff"]] = relationship(
        back_populates="story", cascade="all, delete-orphan"
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
    bias_provenance: Mapped[str] = mapped_column(
        String(50), default="unknown"
    )  # curated, allsides, llm, heuristic
    is_curated_source: Mapped[bool] = mapped_column(Boolean, default=False)
    bias_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    bucket_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    exact_bias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    coverage_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    extractor_method: Mapped[str | None] = mapped_column(String(80), nullable=True)
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    og_image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    embedded_post_urls_json: Mapped[str] = mapped_column(Text, default="[]")
    image_alt_text_json: Mapped[str] = mapped_column(Text, default="[]")
    media_captions_json: Mapped[str] = mapped_column(Text, default="[]")
    relevance_diagnostics_json: Mapped[str] = mapped_column(Text, default="{}")
    media_diagnostics_json: Mapped[str] = mapped_column(Text, default="{}")
    key_framing: Mapped[str] = mapped_column(Text, default="")
    extracted_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)

    # Relationships
    story: Mapped["Story"] = relationship(back_populates="sources")
    semantic_documents: Mapped[list["SemanticDocument"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    source_findings: Mapped[list["SourceFindingRecord"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    visual_evidence_records: Mapped[list["VisualEvidenceRecordModel"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )

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

    # Structured extraction
    structured_claims: Mapped[str] = mapped_column(
        Text, default="{}"
    )  # JSON: FactExtractionResult
    coverage_asymmetry: Mapped[str] = mapped_column(
        Text, default="{}"
    )  # JSON: CoverageAsymmetry
    narrative_json: Mapped[str] = mapped_column(
        Text, default="{}"
    )  # JSON: NarrativeResult

    # Output
    outline: Mapped[str] = mapped_column(Text, default="")
    full_report_md: Mapped[str] = mapped_column(Text, default="")
    full_report_json: Mapped[str] = mapped_column(Text, default="{}")
    coverage_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    candidate_census_json: Mapped[str] = mapped_column(Text, default="{}")
    visual_evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    report_validation_warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    agent_handoff_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)

    # Relationships
    story: Mapped["Story"] = relationship(back_populates="analysis")
    semantic_documents: Mapped[list["SemanticDocument"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )
    source_findings: Mapped[list["SourceFindingRecord"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )
    visual_evidence_records: Mapped[list["VisualEvidenceRecordModel"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )
    agent_findings: Mapped[list["AgentFinding"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )
    agent_handoffs: Mapped[list["AgentHandoff"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Analysis(story_id={self.story_id[:8]})>"


class AnalysisRun(Base):
    """Durable execution record for one analysis attempt."""

    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    story_id: Mapped[str] = mapped_column(String(36), ForeignKey("stories.id"))
    status: Mapped[str] = mapped_column(String(30), default="running")
    options_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    coverage_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    candidate_census_json: Mapped[str] = mapped_column(Text, default="{}")
    report_validation_warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    story: Mapped["Story"] = relationship(back_populates="analysis_runs")
    retrieval_candidates: Mapped[list["RetrievalCandidate"]] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<AnalysisRun(story_id={self.story_id[:8]}, status={self.status})>"


class RetrievalCandidate(Base):
    """Lifecycle diagnostics for one probed retrieval candidate."""

    __tablename__ = "retrieval_candidates"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    analysis_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analysis_runs.id")
    )
    story_id: Mapped[str] = mapped_column(String(36), ForeignKey("stories.id"))
    url: Mapped[str] = mapped_column(String(2048))
    domain: Mapped[str] = mapped_column(String(255), default="")
    title: Mapped[str] = mapped_column(String(500), default="")
    stage: Mapped[str] = mapped_column(String(30), default="unknown")
    state: Mapped[str] = mapped_column(String(40))
    bucket_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    exact_bias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    extractor_method: Mapped[str | None] = mapped_column(String(80), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    relevance_diagnostics_json: Mapped[str] = mapped_column(Text, default="{}")
    source_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    media_diagnostics_json: Mapped[str] = mapped_column(Text, default="{}")
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)

    analysis_run: Mapped["AnalysisRun"] = relationship(
        back_populates="retrieval_candidates"
    )

    def __repr__(self) -> str:
        return f"<RetrievalCandidate(state={self.state}, domain={self.domain})>"


class SourceFindingRecord(Base):
    """Durable per-source finding returned by the report writer."""

    __tablename__ = "source_findings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    story_id: Mapped[str] = mapped_column(String(36), ForeignKey("stories.id"))
    analysis_id: Mapped[str] = mapped_column(String(36), ForeignKey("analyses.id"))
    source_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sources.id"), nullable=True
    )
    source_ref: Mapped[str] = mapped_column(String(20), default="")
    key_framing: Mapped[str] = mapped_column(Text, default="")
    notable_claim: Mapped[str] = mapped_column(Text, default="")
    evidence_snippet: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)

    analysis: Mapped["Analysis"] = relationship(back_populates="source_findings")
    source: Mapped["Source | None"] = relationship(back_populates="source_findings")

    def __repr__(self) -> str:
        return f"<SourceFindingRecord(source_ref={self.source_ref})>"


class VisualEvidenceRecordModel(Base):
    """Durable observable visual/social evidence record."""

    __tablename__ = "visual_evidence_records"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    story_id: Mapped[str] = mapped_column(String(36), ForeignKey("stories.id"))
    analysis_id: Mapped[str] = mapped_column(String(36), ForeignKey("analyses.id"))
    source_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sources.id"), nullable=True
    )
    source_url: Mapped[str] = mapped_column(String(2048))
    media_url: Mapped[str] = mapped_column(String(2048), default="")
    media_type: Mapped[str] = mapped_column(String(50), default="image")
    platform: Mapped[str] = mapped_column(String(80), default="")
    observable_text: Mapped[str] = mapped_column(Text, default="")
    visible_symbols_or_numbers_json: Mapped[str] = mapped_column(Text, default="[]")
    observable_objects_json: Mapped[str] = mapped_column(Text, default="[]")
    reported_context: Mapped[str] = mapped_column(Text, default="")
    interpretation: Mapped[str] = mapped_column(Text, default="")
    legal_characterization: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)

    analysis: Mapped["Analysis"] = relationship(
        back_populates="visual_evidence_records"
    )
    source: Mapped["Source | None"] = relationship(
        back_populates="visual_evidence_records"
    )

    def __repr__(self) -> str:
        return f"<VisualEvidenceRecordModel(media_url={self.media_url[:50]})>"


class AgentFinding(Base):
    """Durable structured finding produced for an analysis agent lane."""

    __tablename__ = "agent_findings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    story_id: Mapped[str] = mapped_column(String(36), ForeignKey("stories.id"))
    analysis_id: Mapped[str] = mapped_column(String(36), ForeignKey("analyses.id"))
    agent_name: Mapped[str] = mapped_column(String(50))
    finding_type: Mapped[str] = mapped_column(String(80))
    finding_text: Mapped[str] = mapped_column(Text, default="")
    source_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)

    story: Mapped["Story"] = relationship(back_populates="agent_findings")
    analysis: Mapped["Analysis"] = relationship(back_populates="agent_findings")

    def __repr__(self) -> str:
        return f"<AgentFinding(agent={self.agent_name}, type={self.finding_type})>"


class AgentHandoff(Base):
    """Durable context bundle passed between retrieval and analysis stages."""

    __tablename__ = "agent_handoffs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    story_id: Mapped[str] = mapped_column(String(36), ForeignKey("stories.id"))
    analysis_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("analyses.id"), nullable=True
    )
    stage: Mapped[str] = mapped_column(String(80))
    from_agent: Mapped[str] = mapped_column(String(50), default="")
    to_agent: Mapped[str] = mapped_column(String(50), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)

    story: Mapped["Story"] = relationship(back_populates="agent_handoffs")
    analysis: Mapped["Analysis | None"] = relationship(back_populates="agent_handoffs")

    def __repr__(self) -> str:
        return f"<AgentHandoff(stage={self.stage}, to={self.to_agent})>"


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

    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now_naive, onupdate=utc_now_naive
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
    owner_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    raw_content: Mapped[str] = mapped_column(Text, default="")
    format: Mapped[str] = mapped_column(String(20), default="yaml")
    parsed_json: Mapped[str] = mapped_column(Text, default="{}")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now_naive, onupdate=utc_now_naive
    )

    def __repr__(self) -> str:
        return f"<ChannelProfile(name={self.name})>"


class DailySpend(Base):
    """Track daily LLM spending for budget enforcement."""

    __tablename__ = "daily_spend"

    date: Mapped[datetime] = mapped_column(
        DateTime, primary_key=True, default=utc_now_naive
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

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now_naive, onupdate=utc_now_naive
    )

    def __repr__(self) -> str:
        return f"<AgentConfiguration(name={self.agent_name}, model={self.model})>"


class SemanticDocument(Base):
    """Canonical text unit that can be chunked for semantic retrieval."""

    __tablename__ = "semantic_documents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    story_id: Mapped[str] = mapped_column(String(36), ForeignKey("stories.id"))
    source_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sources.id"), nullable=True
    )
    analysis_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("analyses.id"), nullable=True
    )
    agent_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    document_type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(500), default="")
    canonical_text: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now_naive, onupdate=utc_now_naive
    )

    story: Mapped["Story"] = relationship(back_populates="semantic_documents")
    source: Mapped["Source | None"] = relationship(back_populates="semantic_documents")
    analysis: Mapped["Analysis | None"] = relationship(
        back_populates="semantic_documents"
    )
    chunks: Mapped[list["SemanticChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<SemanticDocument(type={self.document_type}, story_id={self.story_id[:8]})>"


class SemanticChunk(Base):
    """Chunk of a semantic document with rebuildable vector index metadata."""

    __tablename__ = "semantic_chunks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    semantic_document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("semantic_documents.id")
    )
    story_id: Mapped[str] = mapped_column(String(36), ForeignKey("stories.id"))
    source_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sources.id"), nullable=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_text: Mapped[str] = mapped_column(Text, default="")
    chunk_hash: Mapped[str] = mapped_column(String(64))
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    vector_store_id: Mapped[str] = mapped_column(String(255), default="")
    embedding_provider: Mapped[str] = mapped_column(String(50), default="fake")
    embedding_model: Mapped[str] = mapped_column(String(100), default="fake-hash-v1")
    embedding_dimensions: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)

    document: Mapped["SemanticDocument"] = relationship(back_populates="chunks")

    def __repr__(self) -> str:
        return f"<SemanticChunk(document_id={self.semantic_document_id[:8]}, index={self.chunk_index})>"
