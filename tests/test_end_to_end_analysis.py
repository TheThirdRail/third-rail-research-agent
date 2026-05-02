import json
from pathlib import Path
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core import config as core_config
from src.core.exceptions import SourceExtractionError
from src.database.models import (
    AgentFinding,
    AgentHandoff,
    AnalysisRun,
    Base,
    RetrievalCandidate,
    SemanticDocument,
    Source,
    SourceFindingRecord,
    Story,
    VisualEvidenceRecordModel,
)
from src.schemas.analysis_options import AnalysisOptions
from src.schemas.visual_evidence import VisualEvidenceBundle, VisualEvidenceRecord
from src.services.analysis_service import AnalysisService
from src.services.source_aggregator_service import (
    SourceAggregatorService,
    SourceCandidate,
)
from src.tools.bias_classifier import BiasResult
from src.tools.web_search import SearchResult


def test_end_to_end_seed_url_produces_deterministic_report(monkeypatch, tmp_path: Path):
    class DummySearcher:
        def news_search(self, query: str, max_results: int = 10, time_range: str = "w"):
            return [
                SearchResult(
                    title="CNN covers Biden AI order",
                    url="https://cnn.com/biden-ai-order",
                    snippet="left coverage",
                    source="cnn",
                ),
                SearchResult(
                    title="Fox covers Biden AI order",
                    url="https://foxnews.com/biden-ai-order",
                    snippet="right coverage",
                    source="fox",
                ),
                SearchResult(
                    title="Unrelated sports roundup",
                    url="https://sports.example.com/game",
                    snippet="wrong event",
                    source="sports",
                ),
            ]

        def web_search(self, query: str, max_results: int = 10):
            return []

    def bias_for(domain: str) -> BiasResult:
        mapping = {
            "reuters.com": (0, "Center"),
            "cnn.com": (-2, "Lean Left"),
            "foxnews.com": (3, "Right"),
            "sports.example.com": (0, "Center"),
        }
        bias, label = mapping[domain]
        return BiasResult(
            domain=domain,
            bias=bias,
            bias_label=label,
            confidence=1.0,
            method="dataset",
            factual_rating="high",
            category="mainstream",
        )

    def fake_extract_url(
        self, url: str, require_success: bool = False
    ) -> SourceCandidate:
        domain = urlparse(url).netloc.replace("www.", "")
        if domain == "sports.example.com":
            text = "Football playoffs and player trades dominated the sports desk."
            title = "Sports roundup"
        elif domain == "cnn.com":
            text = (
                "President Joe Biden signed an executive order on AI safety. "
                "CNN emphasized federal standards and civil-liberties concerns."
            )
            title = "CNN examines Biden AI executive order"
        elif domain == "foxnews.com":
            text = (
                "President Joe Biden signed an executive order on AI safety. "
                "Fox News focused on business compliance and regulatory cost."
            )
            title = "Fox covers Biden AI order"
        else:
            text = (
                "President Joe Biden signed an executive order on AI safety. "
                "The order sets standards for federal agencies and technology firms."
            )
            title = "Biden signs executive order on AI safety"
        return SourceCandidate(
            url=url,
            domain=domain,
            title=title,
            published_date=None,
            author=None,
            full_text=text * 8,
            extraction_error=None,
            extractor_method="test_extractor",
            http_status=200,
            bias_result=bias_for(domain),
        )

    test_db = tmp_path / "analysis.db"
    engine = create_engine(
        f"sqlite:///{test_db}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(
        "src.services.analysis_service.get_session",
        lambda: test_session(),
    )
    monkeypatch.setattr(
        SourceAggregatorService,
        "_init_searcher",
        lambda self: DummySearcher(),
    )
    monkeypatch.setattr(SourceAggregatorService, "_extract_url", fake_extract_url)
    monkeypatch.setattr(
        "src.services.rss_retrieval_service.RssRetrievalService.search",
        lambda self, query, *, domains, max_results=8: [],
    )
    monkeypatch.setattr(
        "src.services.analysis_service.run_analysis",
        lambda description,
        url=None,
        prefetched_sources=None,
        visual_evidence_context=None: {
            "sections": {
                "executive_summary": "Crew summary based only on prefetched sources.",
                "what_happened": "President Joe Biden signed an executive order.",
                "agreed_facts": "S1 and S2 report Biden signed the AI order.",
                "source_findings": [
                    {
                        "source_id": "S1",
                        "key_framing": "Frames the order as a federal standards story.",
                        "notable_claim": "The order applies to agencies and firms.",
                        "evidence_snippet": "standards for federal agencies",
                        "confidence": 0.9,
                    }
                ],
            },
            "report": "",
            "story_description": description,
            "story_url": url,
        },
    )

    service = AnalysisService()
    result = service.analyze(
        "President Joe Biden signed executive order on AI safety",
        "https://reuters.com/seed",
    )

    report = result["report"]
    assert result["status"] == "analyzed"
    assert result["coverage_satisfied"]
    assert result["source_count"] == 3
    assert "## Source Matrix" in report
    assert "reuters.com" in report
    assert "cnn.com" in report
    assert "foxnews.com" in report
    assert "sports.example.com" not in report
    assert "## All Sources & Citations" in report
    assert "[^1]:" in report
    with test_session() as session:
        run = (
            session.query(AnalysisRun)
            .filter(AnalysisRun.story_id == result["story_id"])
            .one()
        )
        candidates = (
            session.query(RetrievalCandidate)
            .filter(RetrievalCandidate.analysis_run_id == run.id)
            .all()
        )
        findings = (
            session.query(SourceFindingRecord)
            .filter(SourceFindingRecord.story_id == result["story_id"])
            .all()
        )
        saved_sources = (
            session.query(Source).filter(Source.story_id == result["story_id"]).all()
        )
        agent_findings = (
            session.query(AgentFinding)
            .filter(AgentFinding.story_id == result["story_id"])
            .all()
        )
        handoffs = (
            session.query(AgentHandoff)
            .filter(AgentHandoff.story_id == result["story_id"])
            .all()
        )
    assert run.status == "retrieval_complete"
    assert json.loads(run.options_snapshot_json)["strict_bucket_enforcement"] is True
    assert result["candidate_census"]["by_state"]["retained"] == 3
    assert result["candidate_census"]["by_stage"]["primary"] == 1
    assert {candidate.state for candidate in candidates} >= {
        "retained",
        "relevance_rejected",
    }
    assert len(findings) == 1
    assert findings[0].source_ref == "S1"
    assert findings[0].source_id is not None
    assert "federal standards" in findings[0].key_framing
    source_by_domain = {source.domain: source for source in saved_sources}
    cnn_source = source_by_domain["cnn.com"]
    assert cnn_source.relevance_score is not None
    assert cnn_source.source_score is not None
    assert cnn_source.bucket_label == "left_side"
    assert cnn_source.exact_bias == -2
    assert cnn_source.coverage_type == "direct"
    assert cnn_source.extractor_method is not None
    assert (
        json.loads(cnn_source.relevance_diagnostics_json)["coverage_type"] == "direct"
    )
    assert json.loads(cnn_source.media_diagnostics_json) == {
        "embedded_post_urls": [],
        "image_alt_text_count": 0,
        "media_caption_count": 0,
        "og_image_url": None,
    }
    assert "federal standards" in source_by_domain["reuters.com"].key_framing
    assert {finding.finding_type for finding in agent_findings} >= {
        "fact_claims",
        "coverage_asymmetry",
    }
    fact_finding = next(
        finding for finding in agent_findings if finding.finding_type == "fact_claims"
    )
    assert json.loads(fact_finding.source_refs_json) == ["S1", "S2"]
    assert {handoff.stage for handoff in handoffs} >= {
        "post_retrieval",
        "pre_crew",
        "fact_handoff",
    }
    assert all(handoff.analysis_id is not None for handoff in handoffs)
    diagnostics = AnalysisService().get_diagnostics(result["story_id"])
    assert diagnostics is not None
    assert diagnostics["coverage"]["coverage_satisfied"]
    assert diagnostics["candidate_census"]["by_state"]["retained"] == 3
    assert diagnostics["retrieval_candidates"]
    assert diagnostics["analysis_run"]["options_snapshot"][
        "required_bucket_groups"
    ] == ["left_side", "right_side"]
    post_retrieval = AnalysisService().get_handoff(
        result["story_id"],
        "post_retrieval",
    )
    assert post_retrieval is not None
    assert post_retrieval["payload"]["source_count"] == 3


def test_analysis_service_indexes_retained_sources_when_semantic_memory_enabled(
    monkeypatch,
    tmp_path: Path,
):
    class DummySearcher:
        def news_search(self, query: str, max_results: int = 10, time_range: str = "w"):
            return [
                SearchResult(
                    "CNN covers Biden order", "https://cnn.com/story", "", "cnn"
                ),
                SearchResult(
                    "Fox covers Biden order", "https://foxnews.com/story", "", "fox"
                ),
            ]

        def web_search(self, query: str, max_results: int = 10):
            return []

    def bias_for(domain: str) -> BiasResult:
        mapping = {
            "reuters.com": (0, "Center"),
            "cnn.com": (-2, "Lean Left"),
            "foxnews.com": (3, "Right"),
        }
        bias, label = mapping[domain]
        return BiasResult(
            domain=domain,
            bias=bias,
            bias_label=label,
            confidence=1.0,
            method="dataset",
            factual_rating="high",
            category="mainstream",
        )

    def fake_extract_url(
        self, url: str, require_success: bool = False
    ) -> SourceCandidate:
        domain = urlparse(url).netloc.replace("www.", "")
        return SourceCandidate(
            url=url,
            domain=domain,
            title=f"{domain} title",
            published_date=None,
            author=None,
            full_text=(
                "President Joe Biden signed an executive order on AI safety. "
                f"{domain} covered the regulatory details."
            )
            * 8,
            extraction_error=None,
            extractor_method="test_extractor",
            http_status=200,
            bias_result=bias_for(domain),
        )

    captured: dict[str, object] = {}

    def fake_run_analysis(
        description,
        url=None,
        prefetched_sources=None,
        visual_evidence_context=None,
        agent_contexts=None,
    ):
        captured["agent_contexts"] = agent_contexts
        return {
            "sections": {
                "executive_summary": "Crew summary.",
                "what_happened": "President Joe Biden signed an executive order. S1",
            },
            "report": "",
            "story_description": description,
            "story_url": url,
        }

    test_db = tmp_path / "analysis_semantic.db"
    engine = create_engine(
        f"sqlite:///{test_db}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(
        "src.services.analysis_service.get_session", lambda: test_session()
    )
    monkeypatch.setattr(
        SourceAggregatorService, "_init_searcher", lambda self: DummySearcher()
    )
    monkeypatch.setattr(SourceAggregatorService, "_extract_url", fake_extract_url)
    monkeypatch.setattr(
        "src.services.rss_retrieval_service.RssRetrievalService.search",
        lambda self, query, *, domains, max_results=8: [],
    )
    monkeypatch.setattr(
        "src.services.analysis_service.run_analysis",
        fake_run_analysis,
    )
    monkeypatch.setattr(
        "src.services.analysis_service.VisualEvidenceService.analyze",
        lambda self, pointers: VisualEvidenceBundle(
            records=[
                VisualEvidenceRecord(
                    source_url="https://cnn.com/story",
                    media_url="https://cnn.com/card.jpg",
                    observable_text="AI order graphic",
                    observable_objects=["document graphic"],
                    reported_context="CNN card image metadata",
                    confidence=0.7,
                )
            ]
        ),
    )
    monkeypatch.setattr(core_config.settings, "semantic_memory_enabled", True)
    monkeypatch.setattr(core_config.settings, "embedding_provider", "fake")

    result = AnalysisService().analyze(
        "President Joe Biden signed executive order on AI safety",
        "https://reuters.com/seed",
    )

    with test_session() as session:
        documents = (
            session.query(SemanticDocument)
            .filter(SemanticDocument.story_id == result["story_id"])
            .all()
        )
        visual_records = (
            session.query(VisualEvidenceRecordModel)
            .filter(VisualEvidenceRecordModel.story_id == result["story_id"])
            .all()
        )
        handoffs = (
            session.query(AgentHandoff)
            .filter(AgentHandoff.story_id == result["story_id"])
            .all()
        )

    assert {document.document_type for document in documents} == {
        "seed_story",
        "source_article",
        "visual_evidence",
        "fact_claims",
        "coverage_asymmetry",
    }
    assert len(documents) == 7
    fact_document = next(
        document for document in documents if document.document_type == "fact_claims"
    )
    assert json.loads(fact_document.metadata_json)["source_refs"] == ["S1"]
    assert captured["agent_contexts"]
    assert "fact_extractor" in captured["agent_contexts"]
    assert "semantic_chunk_id=" in captured["agent_contexts"]["fact_extractor"]
    assert "source_ref=S1" in captured["agent_contexts"]["fact_extractor"]
    assert len(visual_records) == 1
    assert visual_records[0].source_id is not None
    assert visual_records[0].observable_text == "AI order graphic"
    assert "pre_crew" in {handoff.stage for handoff in handoffs}


def test_analysis_options_disable_semantic_memory_per_run(monkeypatch, tmp_path: Path):
    class DummySearcher:
        def news_search(self, query: str, max_results: int = 10, time_range: str = "w"):
            return [
                SearchResult("CNN covers Biden order", "https://cnn.com/story", "", "cnn"),
                SearchResult(
                    "Fox covers Biden order", "https://foxnews.com/story", "", "fox"
                ),
            ]

        def web_search(self, query: str, max_results: int = 10):
            return []

    def bias_for(domain: str) -> BiasResult:
        mapping = {
            "reuters.com": (0, "Center"),
            "cnn.com": (-2, "Lean Left"),
            "foxnews.com": (3, "Right"),
        }
        bias, label = mapping[domain]
        return BiasResult(
            domain=domain,
            bias=bias,
            bias_label=label,
            confidence=1.0,
            method="dataset",
            factual_rating="high",
            category="mainstream",
        )

    def fake_extract_url(
        self, url: str, require_success: bool = False
    ) -> SourceCandidate:
        domain = urlparse(url).netloc.replace("www.", "")
        return SourceCandidate(
            url=url,
            domain=domain,
            title=f"{domain} title",
            published_date=None,
            author=None,
            full_text=(
                "President Joe Biden signed an executive order on AI safety. "
                f"{domain} covered the regulatory details."
            )
            * 8,
            extraction_error=None,
            extractor_method="test_extractor",
            http_status=200,
            bias_result=bias_for(domain),
        )

    captured: dict[str, object] = {}

    def fake_run_analysis(
        description,
        url=None,
        prefetched_sources=None,
        visual_evidence_context=None,
        agent_contexts=None,
    ):
        captured["agent_contexts"] = agent_contexts
        return {
            "sections": {
                "executive_summary": "Crew summary.",
                "what_happened": "President Joe Biden signed an executive order. S1",
            },
            "report": "",
            "story_description": description,
            "story_url": url,
        }

    test_db = tmp_path / "analysis_semantic_options.db"
    engine = create_engine(
        f"sqlite:///{test_db}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(
        "src.services.analysis_service.get_session", lambda: test_session()
    )
    monkeypatch.setattr(
        SourceAggregatorService, "_init_searcher", lambda self: DummySearcher()
    )
    monkeypatch.setattr(SourceAggregatorService, "_extract_url", fake_extract_url)
    monkeypatch.setattr(
        "src.services.rss_retrieval_service.RssRetrievalService.search",
        lambda self, query, *, domains, max_results=8: [],
    )
    monkeypatch.setattr("src.services.analysis_service.run_analysis", fake_run_analysis)
    monkeypatch.setattr(core_config.settings, "semantic_memory_enabled", True)
    monkeypatch.setattr(core_config.settings, "embedding_provider", "fake")

    result = AnalysisService().analyze(
        "President Joe Biden signed executive order on AI safety",
        "https://reuters.com/seed",
        options=AnalysisOptions(enable_semantic_memory=False),
    )

    with test_session() as session:
        documents = (
            session.query(SemanticDocument)
            .filter(SemanticDocument.story_id == result["story_id"])
            .all()
        )
        run = (
            session.query(AnalysisRun)
            .filter(AnalysisRun.story_id == result["story_id"])
            .one()
        )

    assert documents == []
    assert captured["agent_contexts"] is None
    assert json.loads(run.options_snapshot_json)["enable_semantic_memory"] is False


def test_failed_retrieval_persists_run_options_and_candidate_diagnostics(
    monkeypatch,
    tmp_path: Path,
):
    class DummySearcher:
        def news_search(self, query: str, max_results: int = 10, time_range: str = "w"):
            return [
                SearchResult("Left A", "https://left-a.example/story", "", "left"),
                SearchResult("Left B", "https://left-b.example/story", "", "left"),
            ]

        def web_search(self, query: str, max_results: int = 10):
            return []

    def fake_extract_url(
        self, url: str, require_success: bool = False
    ) -> SourceCandidate:
        domain = urlparse(url).netloc.replace("www.", "")
        return SourceCandidate(
            url=url,
            domain=domain,
            title=f"{domain} title",
            published_date=None,
            author=None,
            full_text=(
                "President Joe Biden signed an executive order on AI safety. "
                f"{domain} covered the regulatory details."
            )
            * 8,
            extraction_error=None,
            extractor_method="test_extractor",
            http_status=200,
            bias_result=BiasResult(
                domain=domain,
                bias=-2,
                bias_label="Left",
                confidence=1.0,
                method="dataset",
                factual_rating="high",
                category="mainstream",
            ),
        )

    test_db = tmp_path / "analysis_failed_retrieval.db"
    engine = create_engine(
        f"sqlite:///{test_db}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(
        "src.services.analysis_service.get_session", lambda: test_session()
    )
    monkeypatch.setattr(
        SourceAggregatorService, "_init_searcher", lambda self: DummySearcher()
    )
    monkeypatch.setattr(SourceAggregatorService, "_extract_url", fake_extract_url)
    monkeypatch.setattr(
        "src.services.rss_retrieval_service.RssRetrievalService.search",
        lambda self, query, *, domains, max_results=8: [],
    )

    with pytest.raises(SourceExtractionError, match="right_side"):
        AnalysisService().analyze(
            "President Joe Biden signed executive order on AI safety",
            options=AnalysisOptions(
                strict_bucket_enforcement=True,
                required_bucket_groups=["left_side", "right_side"],
            ),
        )

    with test_session() as session:
        story = session.query(Story).one()
        run = session.query(AnalysisRun).filter(AnalysisRun.story_id == story.id).one()
        candidates = (
            session.query(RetrievalCandidate)
            .filter(RetrievalCandidate.analysis_run_id == run.id)
            .all()
        )

    assert story.status == "failed"
    assert run.status == "failed"
    assert run.error == "source_extraction_error"
    options = json.loads(run.options_snapshot_json)
    assert options["strict_bucket_enforcement"] is True
    assert options["required_bucket_groups"] == ["left_side", "right_side"]
    coverage = json.loads(run.coverage_snapshot_json)
    census = json.loads(run.candidate_census_json)
    assert "right_side" in coverage["missing_buckets"]
    assert "right_side" in census["missing_buckets"]
    assert candidates
