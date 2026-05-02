"""Optional LanceDB backend for semantic memory vector search."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from src.core.config import settings
from src.services.vector_store_service import VectorRecord, VectorSearchResult


class LanceDBVectorStore:
    """Local-first LanceDB vector index.

    SQL remains the source of truth. This store only keeps rebuildable chunk
    vectors plus SQL IDs and retrieval metadata.
    """

    backend_name = "lancedb"

    def __init__(
        self,
        *,
        db_path: str | Path | None = None,
        table_name: str | None = None,
    ) -> None:
        try:
            import lancedb  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "LanceDB vector store is configured but the 'lancedb' package "
                "is not installed."
            ) from exc

        self._lancedb = lancedb
        configured_path = getattr(settings, "lancedb_uri", "")
        default_path = settings.data_dir / "vector_store" / "lancedb"
        self._db_path = Path(db_path or configured_path or default_path)
        self._table_name = table_name or getattr(
            settings,
            "lancedb_table_name",
            "semantic_chunks",
        )

    def upsert(self, records: list[VectorRecord]) -> None:
        if not records:
            return
        table = self._open_or_create_table(records[0])
        ids = [record.id for record in records]
        self._delete_ids(table, ids)
        table.add([self._row(record) for record in records])

    def search(
        self,
        query_vector: list[float],
        *,
        story_id: str,
        filters: dict[str, Any] | None = None,
        top_k: int = 4,
    ) -> list[VectorSearchResult]:
        table = self._open_table()
        query = table.search(query_vector).limit(max(1, top_k * 4))
        rows = query.to_list()
        results: list[VectorSearchResult] = []
        for row in rows:
            metadata = self._metadata(row)
            if metadata.get("story_id") != story_id:
                continue
            if not self._matches(metadata, filters or {}):
                continue
            results.append(
                VectorSearchResult(
                    id=str(row.get("id") or metadata.get("semantic_chunk_id") or ""),
                    score=self._score(row),
                    metadata=metadata,
                )
            )
            if len(results) >= top_k:
                break
        return results

    def delete_story(self, story_id: str) -> None:
        try:
            table = self._open_table()
        except RuntimeError:
            return
        self._delete_where(table, f"story_id = '{self._escape(story_id)}'")

    def _open_db(self):
        self._db_path.mkdir(parents=True, exist_ok=True)
        return self._lancedb.connect(str(self._db_path))

    def _open_table(self):
        db = self._open_db()
        try:
            return db.open_table(self._table_name)
        except Exception as exc:
            raise RuntimeError("LanceDB semantic chunk table does not exist") from exc

    def _open_or_create_table(self, sample: VectorRecord):
        db = self._open_db()
        try:
            return db.open_table(self._table_name)
        except Exception:
            return db.create_table(self._table_name, data=[self._row(sample)])

    def _row(self, record: VectorRecord) -> dict[str, Any]:
        metadata = dict(record.metadata)
        for key, value in metadata.items():
            if isinstance(value, (dict, list, tuple, set)):
                metadata[key] = str(value)
        return {
            "id": record.id,
            "vector": record.vector,
            "text": record.text,
            **metadata,
        }

    @staticmethod
    def _metadata(row: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in row.items()
            if key not in {"vector", "_distance", "_score"}
        }

    @staticmethod
    def _score(row: dict[str, Any]) -> float:
        if "_score" in row:
            return float(row["_score"])
        distance = float(row.get("_distance", 0.0) or 0.0)
        if math.isnan(distance):
            return 0.0
        return round(1.0 / (1.0 + max(0.0, distance)), 6)

    @staticmethod
    def _matches(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
        for key, expected in filters.items():
            if expected is None:
                continue
            actual = metadata.get(key)
            if key.endswith("s") and key[:-1] in metadata:
                actual = metadata.get(key[:-1])
            if isinstance(expected, (list, tuple, set, frozenset)):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False
        return True

    @staticmethod
    def _delete_ids(table: Any, ids: list[str]) -> None:
        if not ids:
            return
        quoted = ", ".join(f"'{LanceDBVectorStore._escape(item)}'" for item in ids)
        LanceDBVectorStore._delete_where(table, f"id IN ({quoted})")

    @staticmethod
    def _delete_where(table: Any, where: str) -> None:
        try:
            table.delete(where)
        except Exception:
            return

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("'", "''")
