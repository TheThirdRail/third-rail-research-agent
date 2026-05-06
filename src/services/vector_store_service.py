"""Vector-store abstraction for rebuildable semantic memory indexes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from src.core.config import settings


@dataclass(frozen=True)
class VectorRecord:
    """One chunk embedding plus SQL-linked metadata."""

    id: str
    vector: list[float]
    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class VectorSearchResult:
    """Vector-store search result linked back to a SQL chunk."""

    id: str
    score: float
    metadata: dict[str, Any]


class VectorStore(Protocol):
    """Minimal vector index used by semantic memory."""

    backend_name: str

    def upsert(self, records: list[VectorRecord]) -> None:
        """Insert or replace vector records."""

    def search(
        self,
        query_vector: list[float],
        *,
        story_id: str,
        filters: dict[str, Any] | None = None,
        top_k: int = 4,
    ) -> list[VectorSearchResult]:
        """Search a story-scoped vector index."""

    def delete_story(self, story_id: str) -> None:
        """Delete vector records for one story."""


def get_vector_store(backend_name: str | None = None) -> VectorStore | None:
    """Return the configured vector store, or ``None`` for SQL-only retrieval."""
    backend = (
        (backend_name or getattr(settings, "semantic_vector_store", "none") or "none")
        .strip()
        .lower()
    )
    if backend in {"", "none", "disabled", "sql"}:
        return None
    if backend == "lancedb":
        from src.services.lancedb_vector_store import LanceDBVectorStore

        return LanceDBVectorStore()
    raise ValueError(f"Unsupported semantic vector store: {backend}")
