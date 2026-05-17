"""Optional LanceDB backend for semantic memory vector search."""

from __future__ import annotations

import json
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
        limit = max(1, top_k * 4)
        where_clause = self._where_clause(story_id, filters or {})
        try:
            query = table.search(query_vector)
            if where_clause:
                query = query.where(where_clause)
            rows = query.limit(limit).to_list()
        except Exception:
            rows = table.search(query_vector).limit(limit).to_list()
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
        self._delete_where(table, self._equals("story_id", story_id))

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
            return db.create_table(
                self._table_name,
                schema=self._schema(len(sample.vector)),
            )

    @staticmethod
    def _schema(vector_dimensions: int):
        import pyarrow as pa

        return pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), vector_dimensions)),
                pa.field("text", pa.string()),
                pa.field("story_id", pa.string()),
                pa.field("analysis_id", pa.string()),
                pa.field("semantic_document_id", pa.string()),
                pa.field("semantic_chunk_id", pa.string()),
                pa.field("source_id", pa.string()),
                pa.field("source_ref", pa.string()),
                pa.field("document_type", pa.string()),
                pa.field("domain", pa.string()),
                pa.field("bias_bucket", pa.string()),
                pa.field("exact_bias", pa.string()),
                pa.field("metadata_json", pa.string()),
            ]
        )

    def _row(self, record: VectorRecord) -> dict[str, Any]:
        metadata = dict(record.metadata)
        required = {
            "story_id": self._string_value(metadata.get("story_id")),
            "analysis_id": self._string_value(metadata.get("analysis_id")),
            "semantic_document_id": self._string_value(
                metadata.get("semantic_document_id")
            ),
            "semantic_chunk_id": self._string_value(
                metadata.get("semantic_chunk_id", record.id)
            ),
            "source_id": self._string_value(metadata.get("source_id")),
            "source_ref": self._string_value(metadata.get("source_ref")),
            "document_type": self._string_value(metadata.get("document_type")),
            "domain": self._string_value(metadata.get("domain")),
            "bias_bucket": self._string_value(metadata.get("bias_bucket")),
            "exact_bias": self._string_value(metadata.get("exact_bias")),
        }
        return {
            "id": record.id,
            "vector": record.vector,
            "text": record.text,
            **required,
            "metadata_json": json.dumps(metadata, sort_keys=True, default=str),
        }

    @staticmethod
    def _metadata(row: dict[str, Any]) -> dict[str, Any]:
        metadata_json = row.get("metadata_json")
        parsed: dict[str, Any] = {}
        if metadata_json:
            try:
                loaded = json.loads(str(metadata_json))
                if isinstance(loaded, dict):
                    parsed = loaded
            except json.JSONDecodeError:
                parsed = {}
        row_metadata = {
            key: value
            for key, value in row.items()
            if key not in {"vector", "_distance", "_score", "metadata_json"}
        }
        return {**parsed, **row_metadata}

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
                if actual not in expected and str(actual) not in {
                    str(item) for item in expected
                }:
                    return False
            elif actual != expected and str(actual) != str(expected):
                return False
        return True

    @staticmethod
    def _delete_ids(table: Any, ids: list[str]) -> None:
        if not ids:
            return
        LanceDBVectorStore._delete_where(
            table,
            LanceDBVectorStore._in_values("id", ids),
        )

    @staticmethod
    def _delete_where(table: Any, where: str) -> None:
        try:
            table.delete(where)
        except Exception:
            return

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("'", "''")

    @staticmethod
    def _string_value(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list, tuple, set)):
            return json.dumps(value, sort_keys=True, default=str)
        return str(value)

    @staticmethod
    def _filter_column(key: str) -> str | None:
        aliases = {
            "document_types": "document_type",
            "source_ids": "source_id",
            "source_refs": "source_ref",
            "agent_names": "agent_name",
        }
        column = aliases.get(key, key)
        if column in {
            "story_id",
            "analysis_id",
            "semantic_document_id",
            "semantic_chunk_id",
            "source_id",
            "source_ref",
            "document_type",
            "domain",
            "bias_bucket",
            "exact_bias",
        }:
            return column
        return None

    @staticmethod
    def _equals(column: str, value: Any) -> str:
        return f"{column} = '{LanceDBVectorStore._escape(str(value))}'"

    @staticmethod
    def _in_values(column: str, values: list[Any]) -> str:
        quoted = ", ".join(
            f"'{LanceDBVectorStore._escape(str(item))}'" for item in values
        )
        return f"{column} IN ({quoted})"

    @staticmethod
    def _where_clause(story_id: str, filters: dict[str, Any]) -> str:
        clauses = [LanceDBVectorStore._equals("story_id", story_id)]
        for key, expected in filters.items():
            if expected is None:
                continue
            column = LanceDBVectorStore._filter_column(key)
            if column is None or column == "story_id":
                continue
            if isinstance(expected, (list, tuple, set, frozenset)):
                values = [item for item in expected if item is not None]
                if values:
                    clauses.append(LanceDBVectorStore._in_values(column, values))
            else:
                clauses.append(LanceDBVectorStore._equals(column, expected))
        return " AND ".join(clauses)
