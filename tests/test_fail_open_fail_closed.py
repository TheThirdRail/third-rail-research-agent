"""Tests for fail-open and fail-closed behavior across semantic, vector, and screenshot subsystems.

Verifies that:
- When semantic_fail_open=True, embedding/vector errors fall back silently.
- When semantic_fail_open=False, embedding/vector errors propagate.
- Screenshot capture failures degrade to structured fallbacks, not fatal errors.
"""

import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.core import config as core_config
from src.core.embedding_provider import EmbeddingProvider, FakeEmbeddingProvider
from src.database.models import Base, SemanticChunk, SemanticDocument, Story
from src.schemas.visual_evidence import ScreenshotArtifact
from src.services.screenshot_capture_service import ScreenshotCaptureService
from src.services.semantic_memory_service import SemanticMemoryService
from src.services.source_aggregator_service import (
    SourceAggregatorService,
    SourceCandidate,
)
from src.services.vector_store_service import VectorRecord, VectorSearchResult, VectorStore
from src.tools.bias_classifier import BiasResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_db(tmp_path):
    """Yield a session factory connected to a throwaway SQLite DB."""
    db_path = tmp_path / "failmode.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    yield factory
    engine.dispose()


@pytest.fixture()
def session(test_db):
    """Yield a live database session."""
    s = test_db()
    yield s
    s.close()


class ExplodingEmbeddingProvider(EmbeddingProvider):
    """Embedding provider that always raises."""

    @property
    def provider_name(self) -> str:
        return "exploding"

    @property
    def dimensions(self) -> int:
        return 64

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("Embedding provider unavailable")


class ExplodingVectorStore:
    """Vector store that raises on every operation."""

    backend_name = "exploding"

    def upsert(self, records: list[VectorRecord]) -> None:
        raise RuntimeError("Vector store upsert failed")

    def search(
        self,
        query_vector: list[float],
        *,
        story_id: str,
        filters: dict[str, Any] | None = None,
        top_k: int = 4,
    ) -> list[VectorSearchResult]:
        raise RuntimeError("Vector store search failed")

    def delete_story(self, story_id: str) -> int:
        raise RuntimeError("Vector store delete failed")


def _seed_story(session: Session) -> Story:
    """Insert a minimal story row for testing."""
    from src.schemas.story_packet import StoryPacket

    story = Story(
        id="fail-test-story",
        title="Fail mode test",
        description="Testing fail-open and fail-closed behavior",
        status="pending",
    )
    packet = StoryPacket(
        canonical_headline="Test headline",
        actors=["Actor"],
        action_verbs=["test"],
    )
    story.parsed_metadata = packet.model_dump_json()
    session.add(story)
    session.commit()
    return story


def _make_story_packet():
    from src.schemas.story_packet import StoryPacket

    return StoryPacket(
        canonical_headline="Test headline for fail-mode testing",
        actors=["TestActor"],
        action_verbs=["tested"],
    )


def _make_empty_visual_bundle():
    from src.schemas.visual_evidence import VisualEvidenceBundle

    return VisualEvidenceBundle()


# ---------------------------------------------------------------------------
# Semantic memory fail-open tests (vector store layer)
# ---------------------------------------------------------------------------


class TestSemanticMemoryVectorStoreFailOpen:
    """When semantic_fail_open=True, vector store errors are swallowed."""

    def test_vector_store_upsert_failure_swallowed_fail_open(
        self, session, monkeypatch
    ):
        """Indexing completes even when the vector store upsert explodes."""
        monkeypatch.setattr(core_config.settings, "semantic_fail_open", True)
        story = _seed_story(session)

        svc = SemanticMemoryService(
            session,
            embedding_provider=FakeEmbeddingProvider(),
            vector_store=ExplodingVectorStore(),
        )
        # Should not raise despite exploding vector store
        doc = svc.index_seed_story(story.id, _make_story_packet(), "Seed text.")
        assert doc is not None
        assert doc.story_id == story.id

    def test_delete_story_index_swallows_vector_error_fail_open(
        self, session, monkeypatch
    ):
        monkeypatch.setattr(core_config.settings, "semantic_fail_open", True)
        story = _seed_story(session)

        svc = SemanticMemoryService(
            session,
            embedding_provider=FakeEmbeddingProvider(),
            vector_store=ExplodingVectorStore(),
        )
        # Should not raise
        count = svc.delete_story_index(story.id)
        assert count == 0

    def test_vector_store_search_failure_falls_back_fail_open(
        self, session, monkeypatch
    ):
        """When vector store search fails with fail-open, retrieval still works via ranking."""
        monkeypatch.setattr(core_config.settings, "semantic_fail_open", True)
        story = _seed_story(session)

        # Index with fake embeddings (no vector store) so there's data
        fake_svc = SemanticMemoryService(
            session,
            embedding_provider=FakeEmbeddingProvider(),
            vector_store=None,
        )
        fake_svc.index_seed_story(story.id, _make_story_packet(), "Seed text content.")

        # Now use exploding vector store for retrieval — but with a
        # "real" (non-fake) provider name so the vector path is attempted
        class RealNamedFakeProvider(FakeEmbeddingProvider):
            @property
            def provider_name(self) -> str:
                return "lmstudio"

        svc = SemanticMemoryService(
            session,
            embedding_provider=RealNamedFakeProvider(),
            vector_store=ExplodingVectorStore(),
        )
        # search_similar_to_story calls _rank_chunks_with_vector_store
        # which catches the error and returns None (triggering fallback)
        results = svc.search_similar_to_story(story.id, "query text")
        # Should fall back to _rank_chunks (embedding-based ranking)
        assert isinstance(results, list)


class TestSemanticMemoryRetrievalFailOpen:
    """When semantic_fail_open=True, embedding errors during retrieval fall back."""

    def test_rank_chunks_falls_back_to_lexical_on_embedding_error(
        self, session, monkeypatch
    ):
        """_rank_chunks catches embedding errors and falls back to lexical ranking."""
        monkeypatch.setattr(core_config.settings, "semantic_fail_open", True)
        story = _seed_story(session)

        # Index with fake embeddings first
        fake_svc = SemanticMemoryService(
            session,
            embedding_provider=FakeEmbeddingProvider(),
            vector_store=None,
        )
        fake_svc.index_seed_story(story.id, _make_story_packet(), "Seed text content.")

        # Now try retrieval with exploding embeddings
        exploding_svc = SemanticMemoryService(
            session,
            embedding_provider=ExplodingEmbeddingProvider(),
            vector_store=None,
        )
        # Should fall back to lexical ranking
        results = exploding_svc.search_similar_to_story(story.id, "test query")
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Semantic memory fail-closed tests
# ---------------------------------------------------------------------------


class TestSemanticMemoryVectorStoreFailClosed:
    """When semantic_fail_open=False, errors propagate."""

    def test_vector_store_upsert_failure_raises_fail_closed(
        self, session, monkeypatch
    ):
        monkeypatch.setattr(core_config.settings, "semantic_fail_open", False)
        story = _seed_story(session)

        svc = SemanticMemoryService(
            session,
            embedding_provider=FakeEmbeddingProvider(),
            vector_store=ExplodingVectorStore(),
        )
        with pytest.raises(RuntimeError, match="Vector store upsert failed"):
            svc.index_seed_story(story.id, _make_story_packet(), "Seed text.")

    def test_delete_story_index_raises_on_vector_error_fail_closed(
        self, session, monkeypatch
    ):
        monkeypatch.setattr(core_config.settings, "semantic_fail_open", False)
        story = _seed_story(session)

        svc = SemanticMemoryService(
            session,
            embedding_provider=FakeEmbeddingProvider(),
            vector_store=ExplodingVectorStore(),
        )
        with pytest.raises(RuntimeError, match="Vector store delete failed"):
            svc.delete_story_index(story.id)

    def test_vector_store_search_failure_raises_fail_closed(
        self, session, monkeypatch
    ):
        monkeypatch.setattr(core_config.settings, "semantic_fail_open", False)
        story = _seed_story(session)

        fake_svc = SemanticMemoryService(
            session,
            embedding_provider=FakeEmbeddingProvider(),
            vector_store=None,
        )
        fake_svc.index_seed_story(story.id, _make_story_packet(), "Seed text.")

        class RealNamedFakeProvider(FakeEmbeddingProvider):
            @property
            def provider_name(self) -> str:
                return "lmstudio"

        svc = SemanticMemoryService(
            session,
            embedding_provider=RealNamedFakeProvider(),
            vector_store=ExplodingVectorStore(),
        )
        with pytest.raises(RuntimeError, match="Vector store search failed"):
            svc.search_similar_to_story(story.id, "query text")


class TestSemanticMemoryRetrievalFailClosed:
    """When semantic_fail_open=False, embedding errors during retrieval propagate."""

    def test_rank_chunks_raises_on_embedding_error_fail_closed(
        self, session, monkeypatch
    ):
        monkeypatch.setattr(core_config.settings, "semantic_fail_open", False)
        story = _seed_story(session)

        # Index first
        fake_svc = SemanticMemoryService(
            session,
            embedding_provider=FakeEmbeddingProvider(),
            vector_store=None,
        )
        fake_svc.index_seed_story(story.id, _make_story_packet(), "Seed text.")

        # Now retrieve with exploding embeddings
        exploding_svc = SemanticMemoryService(
            session,
            embedding_provider=ExplodingEmbeddingProvider(),
            vector_store=None,
        )
        with pytest.raises(RuntimeError, match="Embedding provider unavailable"):
            exploding_svc.search_similar_to_story(story.id, "query text")


# ---------------------------------------------------------------------------
# Source aggregator semantic scoring fail-open / fail-closed
# ---------------------------------------------------------------------------


class TestSourceAggregatorSemanticFailOpen:
    """Semantic scoring failures in SourceAggregatorService."""

    def test_build_semantic_scorer_swallows_error_fail_open(self, monkeypatch):
        monkeypatch.setattr(core_config.settings, "semantic_fail_open", True)
        monkeypatch.setattr(core_config.settings, "semantic_candidate_scoring_enabled", True)

        svc = SourceAggregatorService(
            embedding_provider=ExplodingEmbeddingProvider(),
        )
        scorer = svc._build_candidate_semantic_scorer(
            _make_story_packet(), "Seed description"
        )
        # fail-open: swallowed, returns None
        assert scorer is None

    def test_build_semantic_scorer_raises_fail_closed(self, monkeypatch):
        monkeypatch.setattr(core_config.settings, "semantic_fail_open", False)
        monkeypatch.setattr(core_config.settings, "semantic_candidate_scoring_enabled", True)

        svc = SourceAggregatorService(
            embedding_provider=ExplodingEmbeddingProvider(),
        )
        with pytest.raises(RuntimeError, match="Embedding provider unavailable"):
            svc._build_candidate_semantic_scorer(
                _make_story_packet(), "Seed description"
            )

    def test_score_semantic_candidate_swallows_error_fail_open(self, monkeypatch):
        monkeypatch.setattr(core_config.settings, "semantic_fail_open", True)

        class ExplodingScorer:
            def score_candidate_diagnostics(self, title, text):
                raise RuntimeError("Scoring exploded")

        svc = SourceAggregatorService()
        candidate = SourceCandidate(
            url="https://example.com/article",
            domain="example.com",
            title="Test",
            published_date=None,
            author=None,
            full_text="Text",
            extraction_error=None,
            extractor_method="test",
            http_status=200,
            bias_result=BiasResult(
                domain="example.com",
                bias=0,
                bias_label="Center",
                confidence=1.0,
                method="dataset",
                factual_rating="high",
                category="mainstream",
            ),
        )
        result = svc._score_semantic_candidate(ExplodingScorer(), candidate)
        assert result is None

    def test_score_semantic_candidate_raises_fail_closed(self, monkeypatch):
        monkeypatch.setattr(core_config.settings, "semantic_fail_open", False)

        class ExplodingScorer:
            def score_candidate_diagnostics(self, title, text):
                raise RuntimeError("Scoring exploded")

        svc = SourceAggregatorService()
        candidate = SourceCandidate(
            url="https://example.com/article",
            domain="example.com",
            title="Test",
            published_date=None,
            author=None,
            full_text="Text",
            extraction_error=None,
            extractor_method="test",
            http_status=200,
            bias_result=BiasResult(
                domain="example.com",
                bias=0,
                bias_label="Center",
                confidence=1.0,
                method="dataset",
                factual_rating="high",
                category="mainstream",
            ),
        )
        with pytest.raises(RuntimeError, match="Scoring exploded"):
            svc._score_semantic_candidate(ExplodingScorer(), candidate)


# ---------------------------------------------------------------------------
# Screenshot capture fail-open tests
# ---------------------------------------------------------------------------


class TestScreenshotCaptureFailOpen:
    """Screenshot capture failures always degrade to structured fallbacks."""

    def test_disabled_capture_returns_fallback(self, tmp_path):
        svc = ScreenshotCaptureService(enabled=False, artifact_dir=tmp_path)
        result = svc.capture("https://example.com/post")

        assert isinstance(result, ScreenshotArtifact)
        assert result.success is False
        assert result.render_method == "not_configured"
        assert result.fallback_reason == "browser_capture_unavailable"

    def test_private_url_returns_guard_fallback(self, tmp_path):
        svc = ScreenshotCaptureService(enabled=True, artifact_dir=tmp_path)
        result = svc.capture("http://localhost:8080/admin")

        assert isinstance(result, ScreenshotArtifact)
        assert result.success is False
        assert result.render_method == "restricted_url_guard"

    def test_loopback_ip_returns_guard_fallback(self, tmp_path):
        svc = ScreenshotCaptureService(enabled=True, artifact_dir=tmp_path)
        result = svc.capture("http://127.0.0.1:3000/page")

        assert isinstance(result, ScreenshotArtifact)
        assert result.success is False
        assert result.render_method == "restricted_url_guard"

    def test_non_http_url_returns_guard_fallback(self, tmp_path):
        svc = ScreenshotCaptureService(enabled=True, artifact_dir=tmp_path)
        result = svc.capture("ftp://files.example.com/doc")

        assert isinstance(result, ScreenshotArtifact)
        assert result.success is False

    def test_playwright_import_failure_returns_fallback(self, monkeypatch, tmp_path):
        """When Playwright import fails, capture returns structured fallback."""
        svc = ScreenshotCaptureService(enabled=True, artifact_dir=tmp_path)

        # Make the inline `from playwright.sync_api import ...` fail
        # by temporarily removing playwright from sys.modules
        import importlib

        original_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

        def import_blocker(name, *args, **kwargs):
            if "playwright" in name:
                raise ImportError("No module named 'playwright'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", import_blocker)

        result = svc.capture("https://twitter.com/user/status/123")

        assert isinstance(result, ScreenshotArtifact)
        assert result.success is False
        assert "playwright" in result.fallback_reason.lower()


# ---------------------------------------------------------------------------
# Analysis service semantic memory indexing fail-open
# ---------------------------------------------------------------------------


class TestAnalysisServiceSemanticIndexingFailOpen:
    """_index_semantic_memory in AnalysisService swallows errors when fail-open."""

    def test_semantic_indexing_failure_returns_false(self, monkeypatch, tmp_path):
        """AnalysisService._index_semantic_memory returns False on error."""
        from src.services.analysis_service import AnalysisService

        db_path = tmp_path / "indexing.db"
        engine = create_engine(
            f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        monkeypatch.setattr(
            "src.services.analysis_service.get_session",
            lambda: session_factory(),
        )
        monkeypatch.setattr(
            "src.services.analysis_service.SemanticMemoryService.index_seed_story",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                RuntimeError("Semantic indexing boom")
            ),
        )

        svc = AnalysisService()
        result = svc._index_semantic_memory(
            story_id="fake-story-id",
            story_packet=_make_story_packet(),
            description="Test",
            sources=[],
            visual_bundle=_make_empty_visual_bundle(),
            options_snapshot={"enable_semantic_memory": True},
        )
        assert result is False
