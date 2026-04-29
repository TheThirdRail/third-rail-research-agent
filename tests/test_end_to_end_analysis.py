from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base
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
        "src.services.analysis_service.run_analysis",
        lambda description, url=None, prefetched_sources=None: {
            "report": "Crew summary based only on prefetched sources.",
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
