"""Semantic memory service backed by canonical SQL records."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.embedding_provider import EmbeddingProvider, get_embedding_provider
from src.database.models import SemanticChunk, SemanticDocument, Source, Story
from src.schemas.story_packet import StoryPacket
from src.schemas.visual_evidence import VisualEvidenceRecord
from src.services.vector_store_service import (
    VectorRecord,
    VectorStore,
    get_vector_store,
)

AGENT_CONTEXT_TOP_K = 4
AGENT_CONTEXT_EXCERPT_CHARS = 700
AGENT_CONTEXT_MAX_CHARS = 5000
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "what",
    "when",
    "where",
    "who",
    "why",
    "with",
}


@dataclass(frozen=True)
class SemanticRetrievalResult:
    """Source-linked chunk returned by semantic memory retrieval."""

    semantic_chunk_id: str
    semantic_document_id: str
    story_id: str
    source_id: str | None
    chunk_text: str
    similarity: float
    metadata: dict[str, Any]


class SemanticMemoryService:
    """Create semantic documents and rebuildable chunks for a story."""

    def __init__(
        self,
        db: Session,
        embedding_provider: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
        vector_store_backend: str | None = None,
    ) -> None:
        self._db = db
        self._embedding_provider = embedding_provider or get_embedding_provider()
        self._vector_store = vector_store or get_vector_store(vector_store_backend)

    def index_seed_story(
        self,
        story_id: str,
        story_packet: StoryPacket,
        seed_text: str,
        metadata: dict[str, Any] | None = None,
        *,
        analysis_id: str | None = None,
    ) -> SemanticDocument:
        """Create a semantic document and chunks for a parsed seed story."""
        canonical_text = self._seed_story_text(story_packet, seed_text)
        return self._index_document(
            story_id=story_id,
            source_id=None,
            analysis_id=analysis_id,
            agent_name=None,
            document_type="seed_story",
            title=story_packet.canonical_headline,
            canonical_text=canonical_text,
            metadata=metadata or {},
        )

    def index_source_article(
        self,
        story_id: str,
        source_id: str | None,
        title: str,
        text: str,
        metadata: dict[str, Any] | None = None,
        *,
        analysis_id: str | None = None,
    ) -> SemanticDocument:
        """Create a semantic document and chunks for a retained source article."""
        return self._index_document(
            story_id=story_id,
            source_id=source_id,
            analysis_id=analysis_id,
            agent_name=None,
            document_type="source_article",
            title=title,
            canonical_text=text,
            metadata=metadata or {},
        )

    def index_visual_evidence(
        self,
        *,
        story_id: str,
        source_id: str | None,
        record: VisualEvidenceRecord,
        metadata: dict[str, Any] | None = None,
        analysis_id: str | None = None,
    ) -> SemanticDocument:
        """Create semantic memory for visual evidence with separated fields."""
        record_metadata = {
            **(metadata or {}),
            **record.model_dump(),
        }
        title = f"Visual evidence: {record.media_url or record.source_url}"
        return self._index_document(
            story_id=story_id,
            source_id=source_id,
            analysis_id=analysis_id,
            agent_name=None,
            document_type="visual_evidence",
            title=title[:500],
            canonical_text=self._visual_evidence_text(record),
            metadata=record_metadata,
        )

    def index_agent_finding(
        self,
        story_id: str,
        source_id: str | None,
        agent_name: str,
        finding_type: str,
        finding_text: str,
        metadata: dict[str, Any] | None = None,
        analysis_id: str | None = None,
    ) -> SemanticDocument:
        """Create semantic memory for a structured agent finding."""
        return self.index_structured_finding(
            story_id=story_id,
            source_id=source_id,
            analysis_id=analysis_id,
            agent_name=agent_name,
            document_type="agent_finding",
            finding_type=finding_type,
            finding_text=finding_text,
            metadata=metadata,
        )

    def index_structured_finding(
        self,
        *,
        story_id: str,
        source_id: str | None = None,
        analysis_id: str | None = None,
        agent_name: str | None,
        document_type: str,
        finding_type: str,
        finding_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> SemanticDocument:
        """Create semantic memory for a typed structured analysis finding."""
        canonical_text = finding_text.strip()
        if not canonical_text:
            raise ValueError("finding_text is required for semantic memory indexing")
        merged_metadata = {
            "finding_type": finding_type,
            **(metadata or {}),
        }
        return self._index_document(
            story_id=story_id,
            source_id=source_id,
            analysis_id=analysis_id,
            agent_name=agent_name,
            document_type=document_type,
            title=f"{agent_name}: {finding_type}",
            canonical_text=canonical_text,
            metadata=merged_metadata,
        )

    def get_chunks_for_story(self, story_id: str) -> list[SemanticChunk]:
        """Return semantic chunks for a story ordered by document and chunk index."""
        return (
            self._db.query(SemanticChunk)
            .filter(SemanticChunk.story_id == story_id)
            .order_by(SemanticChunk.semantic_document_id, SemanticChunk.chunk_index)
            .all()
        )

    def attach_analysis(self, story_id: str, analysis_id: str) -> int:
        """Attach existing story memory to a persisted analysis record."""
        documents = (
            self._db.query(SemanticDocument)
            .filter(SemanticDocument.story_id == story_id)
            .all()
        )
        indexed_chunks: list[tuple[SemanticChunk, list[float]]] = []
        for document in documents:
            document.analysis_id = analysis_id
            for chunk in document.chunks:
                metadata = self._metadata_for_chunk(chunk)
                metadata["analysis_id"] = analysis_id
                chunk.metadata_json = json.dumps(metadata, sort_keys=True)
                indexed_chunks.append((chunk, []))

        self._db.flush()
        if self._vector_store is not None and indexed_chunks:
            embeddings = self._embed_texts(
                [chunk.chunk_text for chunk, _ in indexed_chunks]
            )
            indexed_chunks = [
                (chunk, embedding)
                for (chunk, _old_embedding), embedding in zip(
                    indexed_chunks,
                    embeddings,
                    strict=True,
                )
            ]
            self._upsert_vector_records(indexed_chunks)
        self._db.commit()
        return len(documents)

    def search_similar_to_story(
        self,
        story_id: str,
        query_text: str,
        filters: dict[str, Any] | None = None,
        top_k: int | None = None,
    ) -> list[SemanticRetrievalResult]:
        """Search story chunks with metadata filters.

        When a vector store is configured, retrieval uses that rebuildable index
        and links results back to SQL chunks. Fake embeddings intentionally fall
        back to lexical ranking so tests and local dry-runs remain deterministic.
        """
        chunks = self._query_chunks(story_id, filters or {})
        vector_ranked = self._rank_chunks_with_vector_store(
            story_id=story_id,
            query_text=query_text,
            chunks=chunks,
            filters=filters or {},
            top_k=self._top_k(top_k),
        )
        if vector_ranked is not None:
            return [
                self._retrieval_result(chunk, similarity)
                for similarity, chunk in vector_ranked
            ]
        ranked = self._rank_chunks(query_text, chunks)
        limit = self._top_k(top_k)
        return [
            self._retrieval_result(chunk, similarity)
            for similarity, chunk in ranked[:limit]
        ]

    def search_for_agent_context(
        self,
        story_id: str,
        agent_name: str,
        task_name: str,
        query_text: str,
        filters: dict[str, Any] | None = None,
        top_k: int | None = None,
    ) -> list[SemanticRetrievalResult]:
        """Retrieve task-specific chunks for a downstream analysis agent."""
        merged_filters = self._agent_context_filters(agent_name, task_name)
        merged_filters.update(filters or {})
        return self.search_similar_to_story(
            story_id=story_id,
            query_text=query_text,
            filters=merged_filters,
            top_k=top_k,
        )

    def build_agent_contexts(
        self,
        story_id: str,
        story_description: str,
        *,
        source_refs: dict[str, str] | None = None,
        top_k: int | None = None,
    ) -> dict[str, str]:
        """Build source-linked semantic context blocks for major analysis tasks."""
        contexts: dict[str, str] = {}
        for agent_name, task_name in (
            ("fact_extractor", "fact_extraction"),
            ("rhetorical_analyst", "rhetoric_analysis"),
            ("narrative_analyzer", "narrative_analysis"),
            ("report_writer", "report_writing"),
        ):
            query_text = self._agent_context_query(
                agent_name,
                task_name,
                story_description,
            )
            results = self.search_for_agent_context(
                story_id=story_id,
                agent_name=agent_name,
                task_name=task_name,
                query_text=query_text,
                top_k=top_k,
            )
            context = self.format_agent_context(
                agent_name=agent_name,
                task_name=task_name,
                results=results,
                source_refs=source_refs,
            )
            if context:
                contexts[agent_name] = context
        return contexts

    def format_agent_context(
        self,
        *,
        agent_name: str,
        task_name: str,
        results: list[SemanticRetrievalResult],
        source_refs: dict[str, str] | None = None,
    ) -> str:
        """Format retrieved chunks for CrewAI prompts without full-article dumps."""
        if not results:
            return ""

        lines = [
            f"SEMANTIC MEMORY CONTEXT: {agent_name} / {task_name}",
            "Use these retrieved chunks as source-linked grounding only.",
        ]
        ordered_results = self._order_context_results(agent_name, results)
        current_bucket: str | None = None
        for result in ordered_results:
            metadata = result.metadata
            bucket = str(metadata.get("bias_bucket") or "unknown")
            if agent_name == "narrative_analyzer" and bucket != current_bucket:
                lines.append(f"Bias bucket: {bucket}")
                current_bucket = bucket

            source_id = result.source_id or "none"
            source_ref = (
                (source_refs or {}).get(result.source_id or "")
                or metadata.get("source_ref")
                or "unmapped"
            )
            lines.append(
                "["
                f"semantic_chunk_id={result.semantic_chunk_id}; "
                f"semantic_document_id={result.semantic_document_id}; "
                f"source_id={source_id}; "
                f"source_ref={source_ref}; "
                f"document_type={metadata.get('document_type', 'unknown')}; "
                f"bias_bucket={bucket}; "
                f"similarity={result.similarity:.3f}"
                "]"
            )
            lines.append(
                self._compact_text(result.chunk_text, AGENT_CONTEXT_EXCERPT_CHARS)
            )

        context = "\n".join(lines)
        if len(context) <= AGENT_CONTEXT_MAX_CHARS:
            return context
        return (
            context[:AGENT_CONTEXT_MAX_CHARS].rstrip()
            + "\n[Semantic context truncated]"
        )

    def delete_story_index(self, story_id: str) -> int:
        """Delete semantic documents/chunks for a story and return document count."""
        documents = (
            self._db.query(SemanticDocument)
            .filter(SemanticDocument.story_id == story_id)
            .all()
        )
        count = len(documents)
        for document in documents:
            self._db.delete(document)
        self._db.commit()
        if self._vector_store is not None:
            try:
                self._vector_store.delete_story(story_id)
            except Exception:
                if not getattr(settings, "semantic_fail_open", True):
                    raise
        return count

    def rebuild_story_index(self, story_id: str) -> list[SemanticDocument]:
        """Rebuild seed and retained source documents from canonical SQL rows."""
        story = self._db.get(Story, story_id)
        if story is None:
            raise ValueError(f"Story not found: {story_id}")
        parsed_packet = StoryPacket.model_validate_json(story.parsed_metadata)

        self.delete_story_index(story_id)
        documents = [
            self.index_seed_story(
                story_id,
                parsed_packet,
                story.description,
                {"rebuild": True},
            )
        ]
        sources = self._db.query(Source).filter(Source.story_id == story_id).all()
        for source in sources:
            documents.append(
                self.index_source_article(
                    story_id=story_id,
                    source_id=source.id,
                    title=source.title,
                    text=source.full_text,
                    metadata={
                        "rebuild": True,
                        "domain": source.domain,
                        "url": source.url,
                        "bias_score": source.political_bias,
                    },
                )
            )
        return documents

    def chunk_text(
        self,
        text: str,
        *,
        max_tokens: int = 900,
        overlap_tokens: int = 100,
    ) -> list[str]:
        """Split text into approximate token chunks using whitespace tokens."""
        tokens = text.split()
        if not tokens:
            return []
        if len(tokens) <= max_tokens:
            return [" ".join(tokens)]

        chunks: list[str] = []
        start = 0
        step = max(1, max_tokens - overlap_tokens)
        while start < len(tokens):
            chunk_tokens = tokens[start : start + max_tokens]
            chunks.append(" ".join(chunk_tokens))
            if start + max_tokens >= len(tokens):
                break
            start += step
        return chunks

    def _query_chunks(
        self,
        story_id: str,
        filters: dict[str, Any],
    ) -> list[SemanticChunk]:
        query = (
            self._db.query(SemanticChunk)
            .join(SemanticDocument)
            .filter(SemanticChunk.story_id == story_id)
        )
        document_types = self._filter_values(filters, "document_type", "document_types")
        if document_types:
            query = query.filter(SemanticDocument.document_type.in_(document_types))
        agent_names = self._filter_values(filters, "agent_name", "agent_names")
        if agent_names:
            query = query.filter(SemanticDocument.agent_name.in_(agent_names))
        source_ids = self._filter_values(filters, "source_id", "source_ids")
        if source_ids:
            query = query.filter(SemanticChunk.source_id.in_(source_ids))

        chunks = query.order_by(
            SemanticDocument.document_type,
            SemanticChunk.source_id,
            SemanticChunk.chunk_index,
        ).all()
        return [chunk for chunk in chunks if self._metadata_matches(chunk, filters)]

    def _rank_chunks(
        self,
        query_text: str,
        chunks: list[SemanticChunk],
    ) -> list[tuple[float, SemanticChunk]]:
        if not chunks:
            return []

        if getattr(self._embedding_provider, "provider_name", "") == "fake":
            return self._rank_chunks_lexically(query_text, chunks)

        retrieval_texts = [self._retrieval_text(chunk) for chunk in chunks]
        try:
            vectors = self._embed_texts([query_text, *retrieval_texts])
            query_vector = vectors[0]
            scored = []
            for chunk, vector, retrieval_text in zip(
                chunks,
                vectors[1:],
                retrieval_texts,
                strict=True,
            ):
                semantic = self._cosine_similarity(query_vector, vector)
                lexical = self._lexical_similarity(query_text, retrieval_text)
                scored.append((round((semantic * 0.85) + (lexical * 0.15), 6), chunk))
            return sorted(scored, key=lambda item: item[0], reverse=True)
        except Exception:
            if not getattr(settings, "semantic_fail_open", True):
                raise
            return self._rank_chunks_lexically(query_text, chunks)

    def _rank_chunks_with_vector_store(
        self,
        *,
        story_id: str,
        query_text: str,
        chunks: list[SemanticChunk],
        filters: dict[str, Any],
        top_k: int,
    ) -> list[tuple[float, SemanticChunk]] | None:
        if self._vector_store is None or not chunks:
            return None
        if getattr(self._embedding_provider, "provider_name", "") == "fake":
            return None

        try:
            query_vector = self._embed_texts([query_text])[0]
            results = self._vector_store.search(
                query_vector,
                story_id=story_id,
                filters=filters,
                top_k=top_k,
            )
        except Exception:
            if not getattr(settings, "semantic_fail_open", True):
                raise
            return None

        if not results:
            return []

        chunks_by_id = {chunk.id: chunk for chunk in chunks}
        ranked: list[tuple[float, SemanticChunk]] = []
        for result in results:
            chunk_id = result.metadata.get("semantic_chunk_id") or result.id
            chunk = chunks_by_id.get(str(chunk_id))
            if chunk is not None:
                ranked.append((round(float(result.score), 6), chunk))
        return ranked

    def _rank_chunks_lexically(
        self,
        query_text: str,
        chunks: list[SemanticChunk],
    ) -> list[tuple[float, SemanticChunk]]:
        scored = [
            (
                self._lexical_similarity(query_text, self._retrieval_text(chunk)),
                chunk,
            )
            for chunk in chunks
        ]
        return sorted(scored, key=lambda item: item[0], reverse=True)

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        batch_size = max(1, int(getattr(settings, "embedding_batch_size", 32)))
        vectors: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            vectors.extend(
                self._embedding_provider.embed_texts(texts[start : start + batch_size])
            )
        return vectors

    def _retrieval_result(
        self,
        chunk: SemanticChunk,
        similarity: float,
    ) -> SemanticRetrievalResult:
        return SemanticRetrievalResult(
            semantic_chunk_id=chunk.id,
            semantic_document_id=chunk.semantic_document_id,
            story_id=chunk.story_id,
            source_id=chunk.source_id,
            chunk_text=chunk.chunk_text,
            similarity=similarity,
            metadata=self._metadata_for_chunk(chunk),
        )

    def _retrieval_text(self, chunk: SemanticChunk) -> str:
        metadata = self._metadata_for_chunk(chunk)
        return "\n".join(
            part
            for part in (
                f"Title: {metadata.get('title', '')}",
                f"Document type: {metadata.get('document_type', '')}",
                f"Domain: {metadata.get('domain', '')}",
                f"Bias bucket: {metadata.get('bias_bucket', '')}",
                chunk.chunk_text,
            )
            if part.strip()
        )

    def _metadata_for_chunk(self, chunk: SemanticChunk) -> dict[str, Any]:
        document = chunk.document
        metadata = {
            **self._json_dict(getattr(document, "metadata_json", "{}")),
            **self._json_dict(chunk.metadata_json),
        }
        metadata.setdefault("document_type", getattr(document, "document_type", ""))
        metadata.setdefault("title", getattr(document, "title", ""))
        metadata.setdefault("agent_name", getattr(document, "agent_name", None))
        metadata.setdefault("story_id", chunk.story_id)
        metadata.setdefault("analysis_id", getattr(document, "analysis_id", None))
        metadata.setdefault("semantic_document_id", chunk.semantic_document_id)
        metadata.setdefault("semantic_chunk_id", chunk.id)
        metadata.setdefault("source_id", chunk.source_id)
        metadata.setdefault("chunk_index", chunk.chunk_index)
        if "bias_bucket" not in metadata and "bias_score" in metadata:
            metadata["bias_bucket"] = self._bias_bucket(metadata.get("bias_score"))
        if "exact_bias" not in metadata:
            source = getattr(document, "source", None)
            metadata["exact_bias"] = metadata.get(
                "bias_score",
                getattr(source, "exact_bias", None) if source is not None else None,
            )
        return metadata

    def _metadata_matches(
        self,
        chunk: SemanticChunk,
        filters: dict[str, Any],
    ) -> bool:
        metadata = self._metadata_for_chunk(chunk)
        known_keys = {
            "document_type",
            "document_types",
            "agent_name",
            "agent_names",
            "source_id",
            "source_ids",
        }
        for key, expected in filters.items():
            if key in known_keys or expected is None:
                continue
            actual = metadata.get(key)
            if isinstance(expected, (list, tuple, set, frozenset)):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False
        return True

    @staticmethod
    def _agent_context_filters(agent_name: str, _task_name: str) -> dict[str, Any]:
        if agent_name == "fact_extractor":
            return {
                "document_types": [
                    "source_article",
                    "visual_evidence",
                    "fact_claims",
                    "agent_finding",
                ]
            }
        if agent_name == "rhetorical_analyst":
            return {
                "document_types": [
                    "source_article",
                    "rhetoric_findings",
                    "agent_finding",
                ]
            }
        if agent_name == "narrative_analyzer":
            return {
                "document_types": [
                    "source_article",
                    "narrative_findings",
                    "coverage_asymmetry",
                    "agent_finding",
                ]
            }
        if agent_name == "report_writer":
            return {
                "document_types": [
                    "source_article",
                    "visual_evidence",
                    "fact_claims",
                    "rhetoric_findings",
                    "narrative_findings",
                    "coverage_asymmetry",
                    "agent_finding",
                ]
            }
        return {"document_types": ["source_article", "agent_finding"]}

    @staticmethod
    def _agent_context_query(
        agent_name: str,
        task_name: str,
        story_description: str,
    ) -> str:
        task_terms = {
            "fact_extractor": "direct factual claims who what when where official quotes procedural details observable evidence",
            "rhetorical_analyst": "headline framing loaded language coded terms opinion interpretation emotional rhetoric",
            "narrative_analyzer": "bias bucket narrative emphasis omissions counter narrative framing differences",
            "report_writer": "citation ready facts source matrix structured findings evidence limitations report synthesis",
        }
        return f"{story_description}\n{task_name}\n{task_terms.get(agent_name, '')}".strip()

    @staticmethod
    def _order_context_results(
        agent_name: str,
        results: list[SemanticRetrievalResult],
    ) -> list[SemanticRetrievalResult]:
        if agent_name != "narrative_analyzer":
            return sorted(results, key=lambda result: result.similarity, reverse=True)
        bucket_order = {"left_side": 0, "center": 1, "right_side": 2}
        return sorted(
            results,
            key=lambda result: (
                bucket_order.get(str(result.metadata.get("bias_bucket")), 99),
                -result.similarity,
            ),
        )

    @staticmethod
    def _filter_values(filters: dict[str, Any], *keys: str) -> list[Any]:
        for key in keys:
            value = filters.get(key)
            if value is None:
                continue
            if isinstance(value, (list, tuple, set, frozenset)):
                return [item for item in value if item is not None]
            return [value]
        return []

    @staticmethod
    def _json_dict(value: str | None) -> dict[str, Any]:
        if not value:
            return {}
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _lexical_similarity(query_text: str, candidate_text: str) -> float:
        query_tokens = SemanticMemoryService._tokens(query_text)
        candidate_tokens = SemanticMemoryService._tokens(candidate_text)
        if not query_tokens or not candidate_tokens:
            return 0.0
        overlap = len(query_tokens & candidate_tokens)
        query_coverage = overlap / len(query_tokens)
        candidate_density = overlap / len(candidate_tokens)
        return round(min(1.0, (query_coverage * 0.85) + (candidate_density * 0.15)), 6)

    @staticmethod
    def _tokens(text: str) -> set[str]:
        tokens = {
            token.lower()
            for token in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9'-]*", text or "")
        }
        return {token for token in tokens if token not in _STOPWORDS and len(token) > 1}

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if len(left) != len(right):
            raise ValueError("Embedding dimension mismatch for semantic retrieval")
        if not left:
            return 0.0

        dot = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return round(max(0.0, min(1.0, dot / (left_norm * right_norm))), 6)

    @staticmethod
    def _bias_bucket(value: Any) -> str:
        try:
            score = int(value)
        except (TypeError, ValueError):
            return "unknown"
        if score <= -1:
            return "left_side"
        if score >= 1:
            return "right_side"
        return "center"

    @staticmethod
    def _top_k(value: int | None) -> int:
        if value is None:
            value = int(getattr(settings, "semantic_top_k", AGENT_CONTEXT_TOP_K))
        return max(1, value)

    @staticmethod
    def _compact_text(text: str, max_chars: int) -> str:
        compacted = re.sub(r"\s+", " ", text or "").strip()
        if len(compacted) <= max_chars:
            return compacted
        return compacted[:max_chars].rstrip() + "..."

    def _index_document(
        self,
        *,
        story_id: str,
        source_id: str | None,
        analysis_id: str | None,
        agent_name: str | None,
        document_type: str,
        title: str,
        canonical_text: str,
        metadata: dict[str, Any],
    ) -> SemanticDocument:
        document = SemanticDocument(
            story_id=story_id,
            source_id=source_id,
            analysis_id=analysis_id,
            agent_name=agent_name,
            document_type=document_type,
            title=title,
            canonical_text=canonical_text,
            metadata_json=json.dumps(metadata, sort_keys=True),
        )
        self._db.add(document)
        self._db.flush()

        chunk_texts = self.chunk_text(canonical_text)
        embeddings = self._embedding_provider.embed_texts(chunk_texts)
        indexed_chunks: list[tuple[SemanticChunk, list[float]]] = []
        for index, (chunk_text, embedding) in enumerate(
            zip(chunk_texts, embeddings, strict=True)
        ):
            chunk = SemanticChunk(
                semantic_document_id=document.id,
                story_id=story_id,
                source_id=source_id,
                chunk_index=index,
                chunk_text=chunk_text,
                chunk_hash=self._chunk_hash(chunk_text),
                token_count=len(chunk_text.split()),
                vector_store_id=f"{self._embedding_provider.provider_name}:{document.id}:{index}",
                embedding_provider=self._embedding_provider.provider_name,
                embedding_model=self._embedding_provider.model_name,
                embedding_dimensions=len(embedding),
                metadata_json=json.dumps(
                    {
                        **metadata,
                        "analysis_id": analysis_id,
                        "document_type": document_type,
                        "agent_name": agent_name,
                        "chunk_index": index,
                    },
                    sort_keys=True,
                ),
            )
            self._db.add(chunk)
            indexed_chunks.append((chunk, embedding))

        self._db.flush()
        self._upsert_vector_records(indexed_chunks)
        self._db.commit()
        self._db.refresh(document)
        return document

    def _upsert_vector_records(
        self,
        indexed_chunks: list[tuple[SemanticChunk, list[float]]],
    ) -> None:
        if self._vector_store is None or not indexed_chunks:
            return
        records = [
            VectorRecord(
                id=chunk.id,
                vector=embedding,
                text=chunk.chunk_text,
                metadata=self._vector_metadata(chunk),
            )
            for chunk, embedding in indexed_chunks
        ]
        try:
            self._vector_store.upsert(records)
        except Exception:
            if not getattr(settings, "semantic_fail_open", True):
                raise

    def _vector_metadata(self, chunk: SemanticChunk) -> dict[str, Any]:
        metadata = self._metadata_for_chunk(chunk)
        source = chunk.document.source
        metadata.update(
            {
                "story_id": chunk.story_id,
                "analysis_id": chunk.document.analysis_id,
                "semantic_document_id": chunk.semantic_document_id,
                "semantic_chunk_id": chunk.id,
                "source_id": chunk.source_id,
                "source_ref": metadata.get("source_ref", ""),
                "document_type": chunk.document.document_type,
                "domain": metadata.get(
                    "domain",
                    getattr(source, "domain", "") if source is not None else "",
                ),
                "bias_bucket": metadata.get("bias_bucket", ""),
                "exact_bias": metadata.get(
                    "exact_bias",
                    metadata.get(
                        "bias_score",
                        getattr(source, "exact_bias", None)
                        if source is not None
                        else None,
                    ),
                ),
            }
        )
        return metadata

    @staticmethod
    def _seed_story_text(story_packet: StoryPacket, seed_text: str) -> str:
        parts = [
            f"Canonical headline: {story_packet.canonical_headline}",
            f"User description: {seed_text}",
            f"Actors: {', '.join(story_packet.actors)}",
            f"Actions: {', '.join(story_packet.action_verbs)}",
            f"Distinctive terms: {', '.join(story_packet.distinctive_terms)}",
            f"Visual descriptors: {', '.join(story_packet.visual_descriptors)}",
            f"Must-have terms: {', '.join(story_packet.must_have_terms)}",
            f"Must-not-have terms: {', '.join(story_packet.must_not_have_terms)}",
            f"Disambiguation notes: {story_packet.disambiguation_notes}",
        ]
        return "\n".join(part for part in parts if part.strip())

    @staticmethod
    def _visual_evidence_text(record: VisualEvidenceRecord) -> str:
        visible_symbols = (
            ", ".join(record.visible_symbols_or_numbers) or "none observed"
        )
        observable_objects = ", ".join(record.observable_objects) or "none observed"
        parts = [
            "Observable content:",
            f"Observable text: {record.observable_text or 'none observed'}",
            f"Visible symbols or numbers: {visible_symbols}",
            f"Observable objects: {observable_objects}",
            "",
            "Reported context:",
            record.reported_context or "none reported",
            "",
            "Interpretation:",
            record.interpretation or "not inferred",
            "",
            "Legal characterization:",
            record.legal_characterization or "not inferred",
            "",
            f"Source URL: {record.source_url}",
            f"Media URL: {record.media_url}",
            f"Media type: {record.media_type}",
            f"Platform: {record.platform or 'unknown'}",
            f"Confidence: {record.confidence:.2f}",
        ]
        return "\n".join(parts)

    @staticmethod
    def _chunk_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
