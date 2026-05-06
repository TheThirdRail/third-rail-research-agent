import pytest

from src.services.lancedb_vector_store import LanceDBVectorStore
from src.services.vector_store_service import VectorRecord

pytest.importorskip("lancedb")


def _record(
    record_id: str,
    *,
    story_id: str = "story-1",
    source_ref: str = "S1",
    document_type: str = "source_article",
    domain: str = "example.com",
    bias_bucket: str = "center",
    exact_bias: int | None = 0,
    vector: list[float] | None = None,
) -> VectorRecord:
    return VectorRecord(
        id=record_id,
        vector=vector or [1.0, 0.0, 0.0],
        text=f"{source_ref} semantic chunk",
        metadata={
            "story_id": story_id,
            "analysis_id": "run-1",
            "semantic_document_id": f"doc-{record_id}",
            "semantic_chunk_id": record_id,
            "source_id": f"source-{source_ref}",
            "source_ref": source_ref,
            "document_type": document_type,
            "domain": domain,
            "bias_bucket": bias_bucket,
            "exact_bias": exact_bias,
            "extra_payload": {"kept": True},
        },
    )


def test_lancedb_vector_store_upserts_searches_and_filters(tmp_path):
    store = LanceDBVectorStore(db_path=tmp_path / "lancedb", table_name="chunks")
    store.upsert(
        [
            _record("chunk-1", source_ref="S1", domain="left.example"),
            _record(
                "chunk-2",
                source_ref="S2",
                domain="right.example",
                bias_bucket="right_side",
                exact_bias=2,
                vector=[0.0, 1.0, 0.0],
            ),
            _record("chunk-3", story_id="story-2", source_ref="S3"),
        ]
    )

    results = store.search(
        [1.0, 0.0, 0.0],
        story_id="story-1",
        filters={"document_types": ["source_article"], "source_refs": ["S1"]},
        top_k=5,
    )

    assert [result.id for result in results] == ["chunk-1"]
    assert results[0].metadata["story_id"] == "story-1"
    assert results[0].metadata["analysis_id"] == "run-1"
    assert results[0].metadata["semantic_document_id"] == "doc-chunk-1"
    assert results[0].metadata["semantic_chunk_id"] == "chunk-1"
    assert results[0].metadata["source_id"] == "source-S1"
    assert results[0].metadata["source_ref"] == "S1"
    assert results[0].metadata["document_type"] == "source_article"
    assert results[0].metadata["domain"] == "left.example"
    assert results[0].metadata["bias_bucket"] == "center"
    assert results[0].metadata["exact_bias"] == "0"
    assert results[0].metadata["extra_payload"] == {"kept": True}


def test_lancedb_vector_store_replaces_existing_ids_without_duplicates(tmp_path):
    store = LanceDBVectorStore(db_path=tmp_path / "lancedb", table_name="chunks")
    store.upsert([_record("chunk-1", source_ref="S1")])
    store.upsert(
        [
            _record(
                "chunk-1",
                source_ref="S1b",
                domain="updated.example",
                vector=[1.0, 0.0, 0.0],
            )
        ]
    )

    results = store.search(
        [1.0, 0.0, 0.0],
        story_id="story-1",
        filters={"source_refs": ["S1b"]},
        top_k=5,
    )
    old_results = store.search(
        [1.0, 0.0, 0.0],
        story_id="story-1",
        filters={"source_refs": ["S1"]},
        top_k=5,
    )

    assert len(results) == 1
    assert results[0].id == "chunk-1"
    assert results[0].metadata["domain"] == "updated.example"
    assert old_results == []


def test_lancedb_vector_store_deletes_one_story_without_touching_others(tmp_path):
    store = LanceDBVectorStore(db_path=tmp_path / "lancedb", table_name="chunks")
    store.upsert(
        [
            _record("chunk-1", story_id="story-1", source_ref="S1"),
            _record("chunk-2", story_id="story-2", source_ref="S2"),
        ]
    )

    store.delete_story("story-1")

    assert store.search([1.0, 0.0, 0.0], story_id="story-1", top_k=5) == []
    remaining = store.search([1.0, 0.0, 0.0], story_id="story-2", top_k=5)
    assert [result.id for result in remaining] == ["chunk-2"]
