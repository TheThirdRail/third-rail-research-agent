"""Semantic-memory indexing orchestration for analysis runs."""

import logging
from typing import Any

from sqlalchemy.orm import Session

from src.core import analysis_events
from src.core.config import settings
from src.core.embedding_provider import get_embedding_provider
from src.database.models import Source
from src.schemas.story_packet import StoryPacket
from src.schemas.visual_evidence import VisualEvidenceBundle
from src.services.analysis_persistence_builder import url_key
from src.services.semantic_memory_service import SemanticMemoryService

logger = logging.getLogger(__name__)


class SemanticAnalysisIndexer:
    """Coordinate semantic-memory writes that hang off an analysis run."""

    def __init__(
        self,
        session: Session,
        semantic_memory_cls: type[SemanticMemoryService] = SemanticMemoryService,
    ) -> None:
        self._session = session
        self._semantic_memory_cls = semantic_memory_cls

    def index_retrieval_context(
        self,
        *,
        story_id: str,
        story_packet: StoryPacket,
        description: str,
        sources: list[tuple[Any, Source]],
        visual_bundle: VisualEvidenceBundle,
        options_snapshot: dict[str, Any] | None = None,
    ) -> bool:
        options_snapshot = options_snapshot or {}
        if not self._enabled(options_snapshot):
            return False
        try:
            semantic_memory = self._semantic_memory(options_snapshot)
            semantic_memory.index_seed_story(
                story_id,
                story_packet,
                description,
                {"stage": "analysis_service"},
            )
            for index, (candidate, source) in enumerate(sources, 1):
                bias = getattr(candidate, "bias_result", None)
                bias_score = source.political_bias
                semantic_memory.index_source_article(
                    story_id=story_id,
                    source_id=source.id,
                    title=source.title,
                    text=source.full_text,
                    metadata={
                        "stage": "analysis_service",
                        "domain": source.domain,
                        "url": source.url,
                        "source_ref": f"S{index}",
                        "bias_score": bias_score,
                        "bias_label": (
                            getattr(bias, "bias_label", None) if bias else None
                        ),
                        "bias_bucket": self.semantic_bias_bucket(bias_score),
                        "coverage_type": getattr(candidate, "coverage_type", None),
                    },
                )
            source_lookup = {
                url_key(candidate.url): (source.id, f"S{index}")
                for index, (candidate, source) in enumerate(sources, 1)
            }
            for index, record in enumerate(visual_bundle.records, 1):
                source_id, source_ref = source_lookup.get(
                    url_key(record.source_url),
                    (None, None),
                )
                semantic_memory.index_visual_evidence(
                    story_id=story_id,
                    source_id=source_id,
                    record=record,
                    metadata={
                        "stage": "analysis_service",
                        "visual_ref": f"V{index}",
                        "source_ref": source_ref,
                    },
                )
            doc_count = 1 + len(sources) + len(visual_bundle.records)
            analysis_events.semantic_memory_chunks_total(
                story_id=story_id,
                chunks=doc_count,
                documents=doc_count,
            )
            logger.info(
                "Semantic memory indexed for story %s: retained_sources=%d visual_records=%d",
                story_id[:8],
                len(sources),
                len(visual_bundle.records),
            )
            return True
        except Exception as exc:
            logger.warning(
                "Semantic memory indexing failed for story %s; continuing: %s",
                story_id[:8],
                exc,
            )
            return False

    def attach_analysis(
        self,
        *,
        story_id: str,
        analysis_id: str,
        options_snapshot: dict[str, Any] | None = None,
    ) -> None:
        options_snapshot = options_snapshot or {}
        if not self._enabled(options_snapshot):
            return
        try:
            attached = self._semantic_memory(options_snapshot).attach_analysis(
                story_id,
                analysis_id,
            )
            logger.info(
                "Semantic memory attached to analysis %s for story %s: documents=%d",
                analysis_id[:8],
                story_id[:8],
                attached,
            )
        except Exception as exc:
            logger.warning(
                "Semantic memory analysis attachment failed for story %s; continuing: %s",
                story_id[:8],
                exc,
            )

    def build_agent_contexts(
        self,
        *,
        story_id: str,
        description: str,
        sources: list[tuple[Any, Source]],
        options_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        try:
            options_snapshot = options_snapshot or {}
            source_refs = {
                source.id: f"S{index}"
                for index, (_candidate, source) in enumerate(sources, 1)
            }
            contexts = self._semantic_memory(options_snapshot).build_agent_contexts(
                story_id,
                description,
                source_refs=source_refs,
            )
            logger.info(
                "Semantic agent contexts built for story %s: agents=%s",
                story_id[:8],
                ",".join(sorted(contexts)),
            )
            return contexts
        except Exception as exc:
            logger.warning(
                "Semantic agent context retrieval failed for story %s; continuing: %s",
                story_id[:8],
                exc,
            )
            return {}

    def index_analysis_findings(
        self,
        *,
        story_id: str,
        analysis_id: str,
        finding_specs: list[dict[str, Any]],
        options_snapshot: dict[str, Any] | None = None,
    ) -> None:
        options_snapshot = options_snapshot or {}
        if not self._enabled(options_snapshot):
            return
        try:
            semantic_memory = self._semantic_memory(options_snapshot)
            indexed = 0
            for spec in finding_specs:
                semantic_memory.index_structured_finding(
                    story_id=story_id,
                    analysis_id=analysis_id,
                    agent_name=spec["agent_name"],
                    document_type=spec["document_type"],
                    finding_type=spec["finding_type"],
                    finding_text=spec["text"],
                    metadata={
                        "stage": "analysis_service",
                        "section_fields": spec["section_fields"],
                        "source_refs": spec["source_refs"],
                    },
                )
                indexed += 1
            logger.info(
                "Semantic analysis findings indexed for story %s: documents=%d",
                story_id[:8],
                indexed,
            )
        except Exception as exc:
            logger.warning(
                "Semantic analysis finding indexing failed for story %s; continuing: %s",
                story_id[:8],
                exc,
            )

    def _semantic_memory(
        self,
        options_snapshot: dict[str, Any],
    ) -> SemanticMemoryService:
        return self._semantic_memory_cls(
            self._session,
            embedding_provider=get_embedding_provider(
                options_snapshot.get("embedding_provider"),
                options_snapshot.get("embedding_model"),
            ),
            vector_store_backend=options_snapshot.get("vector_store"),
        )

    @staticmethod
    def _enabled(options_snapshot: dict[str, Any]) -> bool:
        return bool(
            options_snapshot.get(
                "enable_semantic_memory",
                getattr(settings, "semantic_memory_enabled", False),
            )
        )

    @staticmethod
    def semantic_bias_bucket(bias_score: int) -> str:
        if bias_score <= -1:
            return "left_side"
        if bias_score >= 1:
            return "right_side"
        return "center"
