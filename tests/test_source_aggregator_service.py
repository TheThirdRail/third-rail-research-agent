from unittest.mock import patch
from urllib.parse import urlparse

from src.schemas.story_packet import StoryPacket
from src.services.source_aggregator_service import (
    SourceAggregatorService,
    SourceCandidate,
)
from src.tools.bias_classifier import BiasResult
from src.tools.web_search import SearchResult


def test_gather_sources_continues_when_seed_url_unextractable(monkeypatch):
    class DummySearcher:
        def news_search(self, query: str, max_results: int = 10, time_range: str = "m"):
            return [
                SearchResult(
                    title="Left source",
                    url="https://left.example.com/story-a",
                    snippet="left snippet",
                    source="left",
                ),
                SearchResult(
                    title="Right source",
                    url="https://right.example.com/story-b",
                    snippet="right snippet",
                    source="right",
                ),
                SearchResult(
                    title="Center source",
                    url="https://center.example.com/story-c",
                    snippet="center snippet",
                    source="center",
                ),
            ]

        def web_search(self, query: str, max_results: int = 10):
            return []

    monkeypatch.setattr(
        SourceAggregatorService, "_init_searcher", lambda self: DummySearcher()
    )
    monkeypatch.setattr(
        SourceAggregatorService,
        "_resolve_bias",
        lambda self, domain, url, text: None,
    )

    def fake_extract_url(
        self, url: str, require_success: bool = False
    ) -> SourceCandidate:
        domain = urlparse(url).netloc.replace("www.", "")
        if "nytimes.com" in domain:
            return SourceCandidate(
                url=url,
                domain=domain,
                title="",
                published_date=None,
                author=None,
                full_text="",
                extraction_error="No content extracted via Playwright",
                bias_result=None,
            )
        return SourceCandidate(
            url=url,
            domain=domain,
            title="Recovered source",
            published_date=None,
            author=None,
            full_text="x" * 500,
            extraction_error=None,
            bias_result=None,
        )

    monkeypatch.setattr(SourceAggregatorService, "_extract_url", fake_extract_url)

    # Override retained_source_min to match test fixture (3 available search results)
    with patch("src.services.source_aggregator_service.settings") as mock_settings:
        mock_settings.retained_source_min = 2
        mock_settings.retained_source_max = 15
        mock_settings.candidate_probe_limit = 50
        mock_settings.rss_seed_fallback_enabled = True
        mock_settings.searxng_base_url = ""
        mock_settings.searxng_api_key = ""

        service = SourceAggregatorService()
        sources = service.gather_sources(
            description="Xi phone call taiwan",
            url="https://www.nytimes.com/2026/02/04/us/politics/xi-phone-call-taiwan.html",
        )

    assert len(sources) >= 2
    assert all(src.full_text for src in sources)
    assert all("nytimes.com" not in src.domain for src in sources)


def test_gather_sources_uses_planner_and_relevance_scorer(monkeypatch):
    class DummySearcher:
        def __init__(self):
            self.queries = []

        def news_search(self, query: str, max_results: int = 10, time_range: str = "w"):
            self.queries.append(query)
            return [
                SearchResult(
                    title="CNN covers Biden order",
                    url="https://cnn.com/biden-ai-order",
                    snippet="left",
                    source="cnn",
                ),
                SearchResult(
                    title="Fox covers Biden order",
                    url="https://foxnews.com/biden-ai-order",
                    snippet="right",
                    source="fox",
                ),
                SearchResult(
                    title="Sports roundup",
                    url="https://sports.example.com/game",
                    snippet="wrong event",
                    source="sports",
                ),
            ]

        def web_search(self, query: str, max_results: int = 10):
            self.queries.append(query)
            return []

    searcher = DummySearcher()

    monkeypatch.setattr(
        SourceAggregatorService, "_init_searcher", lambda self: searcher
    )

    def bias_for(domain: str) -> BiasResult | None:
        mapping = {
            "reuters.com": (0, "Center"),
            "cnn.com": (-2, "Lean Left"),
            "foxnews.com": (3, "Right"),
            "sports.example.com": (0, "Center"),
        }
        if domain not in mapping:
            return None
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

    monkeypatch.setattr(SourceAggregatorService, "_extract_url", fake_extract_url)

    story_packet = StoryPacket(
        canonical_headline="President Joe Biden signed executive order on AI safety",
        actors=["President Joe Biden"],
        action_verbs=["signed"],
        must_have_terms=["President Joe Biden", "signed"],
        query_pack=["President Joe Biden signed AI safety"],
    )

    service = SourceAggregatorService()
    sources = service.gather_sources(
        description="President Joe Biden signed executive order on AI safety",
        url="https://reuters.com/seed",
        story_packet=story_packet,
    )
    coverage = service.summarize_coverage(sources)

    domains = {source.domain for source in sources}
    assert {"reuters.com", "cnn.com", "foxnews.com"} <= domains
    assert "sports.example.com" not in domains
    assert coverage["coverage_satisfied"]
    assert any(query.startswith("site:") for query in searcher.queries)


def test_format_sources_context_caps_large_article_text():
    service = SourceAggregatorService()
    sources = [
        SourceCandidate(
            url=f"https://example{i}.com/story",
            domain=f"example{i}.com",
            title=f"Example Source {i}",
            published_date=None,
            author=None,
            full_text=("This is a very long extracted article body. " * 500),
            extraction_error=None,
            bias_result=None,
        )
        for i in range(1, 6)
    ]

    context = service.format_sources_context(sources)

    assert len(context) <= 7100
    assert "Use the excerpts as grounding" in context
    assert "This is a very long extracted article body." in context
