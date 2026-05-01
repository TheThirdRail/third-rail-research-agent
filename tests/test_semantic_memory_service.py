import json

import httpx
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from src.core.embedding_provider import FakeEmbeddingProvider, LMStudioEmbeddingProvider
from src.database.models import Base, SemanticChunk, SemanticDocument, Source, Story
from src.schemas.story_packet import StoryPacket
from src.schemas.visual_evidence import VisualEvidenceRecord
from src.services.candidate_semantic_scorer import CandidateSemanticScorer
from src.services.semantic_memory_service import SemanticMemoryService


def test_semantic_tables_are_created_by_metadata(tmp_path):
    db_path = tmp_path / "semantic_schema.db"
    engine = create_engine(f"sqlite:///{db_path}")

    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    assert "semantic_documents" in inspector.get_table_names()
    assert "semantic_chunks" in inspector.get_table_names()


def test_fake_embedding_provider_is_deterministic():
    provider = FakeEmbeddingProvider()

    first = provider.embed_texts(["same text"])[0]
    second = provider.embed_texts(["same text"])[0]

    assert first == second
    assert len(first) == provider.dimensions


def test_lmstudio_embedding_provider_posts_openai_compatible_payload(monkeypatch):
    calls = []

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {"embedding": [0.1, 0.2, 0.3]},
                    {"embedding": [0.4, 0.5, 0.6]},
                ]
            }

    class DummyClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def post(self, url, headers, json):
            calls.append({"url": url, "headers": headers, "json": json})
            return DummyResponse()

    monkeypatch.setattr(httpx, "Client", DummyClient)

    provider = LMStudioEmbeddingProvider(
        model_name="text-embedding-test",
        base_url="http://localhost:1234/v1",
        api_key="local-key",
    )
    vectors = provider.embed_texts(["first", "second"])

    assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    assert provider.dimensions == 3
    assert calls == [
        {
            "url": "http://localhost:1234/v1/embeddings",
            "headers": {"Authorization": "Bearer local-key"},
            "json": {"model": "text-embedding-test", "input": ["first", "second"]},
        }
    ]


def test_candidate_semantic_scorer_indexes_seed_and_scores_candidate():
    class KeywordEmbeddingProvider:
        provider_name = "keyword"
        model_name = "keyword-v1"
        dimensions = 3

        def embed_texts(self, texts: list[str]) -> list[list[float]]:
            vectors = []
            for text in texts:
                lowered = text.lower()
                if "sports" in lowered:
                    vectors.append([0.0, 1.0, 0.0])
                elif "cuba" in lowered or "embargo" in lowered:
                    vectors.append([1.0, 0.0, 0.0])
                else:
                    vectors.append([0.0, 0.0, 1.0])
            return vectors

    packet = StoryPacket(
        canonical_headline="Senate Republicans reject Cuba blockade change",
        actors=["Senate Republicans"],
        action_verbs=["reject"],
        distinctive_terms=["Cuba"],
        must_have_terms=["Senate Republicans", "Cuba"],
        query_pack=["Senate Republicans Cuba blockade"],
    )

    scorer = CandidateSemanticScorer(
        packet,
        "Senate Republicans reject attempt to end Cuba blockade",
        KeywordEmbeddingProvider(),
    )

    assert scorer.seed.run_id
    assert scorer.score_candidate(
        "GOP senators keep Cuba embargo",
        "GOP senators voted to maintain Cuba sanctions.",
    ) == 1.0
    scores = scorer.score_candidate_diagnostics(
        "GOP senators keep Cuba embargo",
        "GOP senators voted to maintain Cuba sanctions.",
    )
    assert scores.aggregate_similarity == 1.0
    assert scores.title_similarity == 1.0
    assert scores.lede_similarity == 1.0
    assert scorer.score_candidate(
        "Sports roundup",
        "Sports playoffs dominated the evening schedule.",
    ) == 0.0


def test_semantic_memory_indexes_seed_story_and_chunks(tmp_path):
    db_path = tmp_path / "semantic_memory.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        story = Story(title="Cuba sanctions vote", description="seed")
        session.add(story)
        session.commit()
        session.refresh(story)

        packet = StoryPacket(
            canonical_headline="Senate Republicans reject Cuba sanctions vote",
            actors=["Senate Republicans"],
            action_verbs=["reject"],
            distinctive_terms=["Cuba"],
            must_have_terms=["Senate Republicans", "Cuba"],
            query_pack=["Senate Republicans Cuba sanctions"],
        )

        service = SemanticMemoryService(session)
        document = service.index_seed_story(
            story.id,
            packet,
            "Senate Republicans rejected an attempt to end Cuba sanctions.",
            {"source": "test"},
        )

        chunks = (
            session.query(SemanticChunk)
            .filter(SemanticChunk.semantic_document_id == document.id)
            .all()
        )

        assert document.document_type == "seed_story"
        assert chunks
        assert chunks[0].vector_store_id.startswith("fake:")
        assert chunks[0].embedding_provider == "fake"
        assert chunks[0].embedding_dimensions == 16
        assert json.loads(chunks[0].metadata_json)["document_type"] == "seed_story"


def test_semantic_memory_indexes_source_article_with_overlap_chunks(tmp_path):
    db_path = tmp_path / "semantic_source.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        story = Story(title="Long story", description="seed")
        session.add(story)
        session.commit()
        session.refresh(story)

        service = SemanticMemoryService(session)
        text = " ".join(f"token{i}" for i in range(1200))
        document = service.index_source_article(
            story_id=story.id,
            source_id=None,
            title="Long article",
            text=text,
            metadata={"domain": "example.com"},
        )

        saved_document = session.get(SemanticDocument, document.id)
        chunks = (
            session.query(SemanticChunk)
            .filter(SemanticChunk.semantic_document_id == document.id)
            .order_by(SemanticChunk.chunk_index)
            .all()
        )

        assert saved_document is not None
        assert saved_document.document_type == "source_article"
        assert len(chunks) == 2
        assert chunks[0].token_count == 900
        assert chunks[1].chunk_text.startswith("token800 ")


def test_semantic_memory_search_returns_source_linked_chunks(tmp_path):
    db_path = tmp_path / "semantic_search.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        story = Story(title="AI order", description="seed")
        session.add(story)
        session.commit()
        session.refresh(story)

        matching_source = Source(
            story_id=story.id,
            domain="example.com",
            url="https://example.com/ai-order",
            title="AI safety order",
            full_text="President Biden signed an AI safety executive order.",
            political_bias=0,
        )
        unrelated_source = Source(
            story_id=story.id,
            domain="sports.example",
            url="https://sports.example/story",
            title="Sports roundup",
            full_text="The playoff game went to overtime.",
            political_bias=2,
        )
        session.add_all([matching_source, unrelated_source])
        session.commit()

        service = SemanticMemoryService(session)
        service.index_source_article(
            story_id=story.id,
            source_id=matching_source.id,
            title=matching_source.title,
            text=matching_source.full_text,
            metadata={
                "domain": matching_source.domain,
                "source_ref": "S1",
                "bias_score": matching_source.political_bias,
            },
        )
        service.index_source_article(
            story_id=story.id,
            source_id=unrelated_source.id,
            title=unrelated_source.title,
            text=unrelated_source.full_text,
            metadata={
                "domain": unrelated_source.domain,
                "source_ref": "S2",
                "bias_score": unrelated_source.political_bias,
            },
        )

        results = service.search_similar_to_story(
            story.id,
            "AI safety executive order federal standards",
            filters={"document_types": ["source_article"]},
            top_k=1,
        )

        assert len(results) == 1
        assert results[0].source_id == matching_source.id
        assert results[0].semantic_chunk_id
        assert results[0].semantic_document_id
        assert results[0].metadata["source_ref"] == "S1"
        assert results[0].metadata["bias_bucket"] == "center"


def test_semantic_memory_builds_agent_contexts_without_full_article_dumps(tmp_path):
    db_path = tmp_path / "semantic_agent_context.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        story = Story(title="AI order", description="seed")
        session.add(story)
        session.commit()
        session.refresh(story)

        left_source = Source(
            story_id=story.id,
            domain="left.example",
            url="https://left.example/ai-order",
            title="Left source",
            full_text="AI safety order source text.",
            political_bias=-2,
        )
        right_source = Source(
            story_id=story.id,
            domain="right.example",
            url="https://right.example/ai-order",
            title="Right source",
            full_text="AI safety order source text.",
            political_bias=3,
        )
        session.add_all([left_source, right_source])
        session.commit()

        service = SemanticMemoryService(session)
        long_text = (
            "President Biden signed an AI safety executive order with federal "
            "standards and agency deadlines. "
        ) * 80
        service.index_source_article(
            story_id=story.id,
            source_id=left_source.id,
            title=left_source.title,
            text=long_text,
            metadata={
                "domain": left_source.domain,
                "source_ref": "S1",
                "bias_score": left_source.political_bias,
            },
        )
        service.index_source_article(
            story_id=story.id,
            source_id=right_source.id,
            title=right_source.title,
            text="Right outlet framed the AI order around regulatory cost.",
            metadata={
                "domain": right_source.domain,
                "source_ref": "S2",
                "bias_score": right_source.political_bias,
            },
        )
        service.index_agent_finding(
            story_id=story.id,
            source_id=left_source.id,
            agent_name="fact_extractor",
            finding_type="agreed_fact",
            finding_text="Both sources report that Biden signed an AI safety order.",
            metadata={"source_ref": "S1"},
        )

        contexts = service.build_agent_contexts(
            story.id,
            "President Biden signed an AI safety executive order",
            source_refs={left_source.id: "S1", right_source.id: "S2"},
            top_k=3,
        )
        report_results = service.search_for_agent_context(
            story_id=story.id,
            agent_name="report_writer",
            task_name="report_writing",
            query_text="citation ready structured findings agreed fact AI order",
            top_k=3,
        )

        assert set(contexts) == {
            "fact_extractor",
            "rhetorical_analyst",
            "narrative_analyzer",
            "report_writer",
        }
        assert "semantic_chunk_id=" in contexts["fact_extractor"]
        assert "source_id=" in contexts["fact_extractor"]
        assert "source_ref=S1" in contexts["fact_extractor"]
        assert "Bias bucket: left_side" in contexts["narrative_analyzer"]
        assert len(contexts["fact_extractor"]) < 5000
        assert any(
            result.metadata["document_type"] == "agent_finding"
            for result in report_results
        )


def test_semantic_memory_indexes_visual_evidence_with_separated_fields(tmp_path):
    db_path = tmp_path / "semantic_visual_evidence.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        story = Story(title="Comey post", description="seed")
        session.add(story)
        session.commit()
        session.refresh(story)

        source = Source(
            story_id=story.id,
            domain="example.com",
            url="https://example.com/comey-post",
            title="Comey post coverage",
            full_text="Coverage of a social media post.",
            political_bias=0,
        )
        session.add(source)
        session.commit()
        session.refresh(source)

        service = SemanticMemoryService(session)
        document = service.index_visual_evidence(
            story_id=story.id,
            source_id=source.id,
            record=VisualEvidenceRecord(
                source_url=source.url,
                media_url="https://example.com/card.jpg",
                platform="x",
                observable_text="Shells arranged as 8647",
                visible_symbols_or_numbers=["8647"],
                observable_objects=["seashells"],
                reported_context="Article says the image came from an X post.",
                interpretation="Some sources characterized the number as threatening.",
                legal_characterization="Some sources discussed a threat allegation.",
                confidence=0.82,
            ),
            metadata={"source_ref": "S1", "visual_ref": "V1"},
        )

        chunk = (
            session.query(SemanticChunk)
            .filter(SemanticChunk.semantic_document_id == document.id)
            .one()
        )
        metadata = json.loads(chunk.metadata_json)
        results = service.search_for_agent_context(
            story_id=story.id,
            agent_name="fact_extractor",
            task_name="fact_extraction",
            query_text="observable evidence shells 8647",
            top_k=1,
        )

        assert document.document_type == "visual_evidence"
        assert metadata["observable_text"] == "Shells arranged as 8647"
        assert metadata["interpretation"].startswith("Some sources characterized")
        assert metadata["legal_characterization"].startswith("Some sources discussed")
        assert "Observable content:" in chunk.chunk_text
        assert "Interpretation:" in chunk.chunk_text
        assert "Legal characterization:" in chunk.chunk_text
        assert results[0].metadata["document_type"] == "visual_evidence"
        assert results[0].source_id == source.id


def test_semantic_memory_retrieves_typed_agent_findings_by_task(tmp_path):
    db_path = tmp_path / "semantic_typed_findings.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        story = Story(title="AI order", description="seed")
        session.add(story)
        session.commit()
        session.refresh(story)

        service = SemanticMemoryService(session)
        service.index_structured_finding(
            story_id=story.id,
            agent_name="fact_extractor",
            document_type="fact_claims",
            finding_type="agreed_facts",
            finding_text="Agreed fact: Biden signed an AI safety order.",
            metadata={"source_ref": "S1"},
        )
        service.index_structured_finding(
            story_id=story.id,
            agent_name="rhetorical_analyst",
            document_type="rhetoric_findings",
            finding_type="loaded_language",
            finding_text="Rhetoric finding: one source used loaded language.",
            metadata={"source_ref": "S2"},
        )
        service.index_structured_finding(
            story_id=story.id,
            agent_name="narrative_analyzer",
            document_type="narrative_findings",
            finding_type="narrative_pattern",
            finding_text="Narrative finding: outlets emphasized different costs.",
            metadata={"bias_bucket": "right_side"},
        )
        service.index_structured_finding(
            story_id=story.id,
            agent_name="narrative_analyzer",
            document_type="coverage_asymmetry",
            finding_type="coverage_asymmetry",
            finding_text="Coverage asymmetry: right-side coverage was sparse.",
            metadata={"missing_buckets": ["right_side"]},
        )

        fact_results = service.search_for_agent_context(
            story_id=story.id,
            agent_name="fact_extractor",
            task_name="fact_extraction",
            query_text="agreed fact AI safety order",
        )
        rhetoric_results = service.search_for_agent_context(
            story_id=story.id,
            agent_name="rhetorical_analyst",
            task_name="rhetoric_analysis",
            query_text="loaded language rhetoric",
        )
        narrative_results = service.search_for_agent_context(
            story_id=story.id,
            agent_name="narrative_analyzer",
            task_name="narrative_analysis",
            query_text="coverage asymmetry narrative",
            top_k=4,
        )

        assert fact_results[0].metadata["document_type"] == "fact_claims"
        assert rhetoric_results[0].metadata["document_type"] == "rhetoric_findings"
        assert {
            result.metadata["document_type"] for result in narrative_results
        } >= {"narrative_findings", "coverage_asymmetry"}


def test_semantic_memory_delete_and_rebuild_story_index(tmp_path):
    db_path = tmp_path / "semantic_rebuild.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        story = Story(
            title="Cuba sanctions vote",
            description="Senate Republicans rejected an attempt to end Cuba sanctions.",
        )
        packet = StoryPacket(
            canonical_headline="Senate Republicans reject Cuba sanctions vote",
            actors=["Senate Republicans"],
            action_verbs=["reject"],
            distinctive_terms=["Cuba"],
            must_have_terms=["Senate Republicans", "Cuba"],
            query_pack=["Senate Republicans Cuba sanctions"],
        )
        story.parsed_metadata = packet.model_dump_json()
        session.add(story)
        session.commit()
        session.refresh(story)

        source = Source(
            story_id=story.id,
            domain="example.com",
            url="https://example.com/story",
            title="Example story",
            full_text="Example source text about the Cuba sanctions vote.",
            political_bias=1,
        )
        session.add(source)
        session.commit()

        service = SemanticMemoryService(session)
        documents = service.rebuild_story_index(story.id)
        chunks = service.get_chunks_for_story(story.id)

        assert {document.document_type for document in documents} == {
            "seed_story",
            "source_article",
        }
        assert len(chunks) == 2
        assert service.delete_story_index(story.id) == 2
        assert service.get_chunks_for_story(story.id) == []
