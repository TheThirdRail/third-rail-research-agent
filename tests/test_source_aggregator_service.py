import time
from threading import Lock
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlparse

from src.schemas.retrieval_diagnostics import CandidateDecision
from src.schemas.story_packet import StoryPacket
from src.services.balanced_source_planner import BucketSpec, SourcePlan
from src.services.source_aggregator_service import (
    QueryAttempt,
    SourceAggregatorService,
    SourceCandidate,
)
from src.services.source_scoring import ScoredCandidate
from src.tools.bias_classifier import BiasResult
from src.tools.web_search import SearchResult


class NoopRssRetriever:
    def search(self, query: str, *, domains: list[str], max_results: int = 8):
        return []

    def search_story(self, story_packet, bucket_spec, *, max_results: int = 8):
        return []


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
        mock_settings.strict_bucket_enforcement = False
        mock_settings.max_per_exact_bias = 10
        mock_settings.max_per_bucket_group = 10
        mock_settings.allow_same_bias_backfill = True

        service = SourceAggregatorService()
        service._rss_retriever = NoopRssRetriever()
        sources = service.gather_sources(
            description="Xi phone call taiwan",
            url="https://www.nytimes.com/2026/02/04/us/politics/xi-phone-call-taiwan.html",
        )

    assert len(sources) >= 2
    assert all(src.full_text for src in sources)
    assert all("nytimes.com" not in src.domain for src in sources)
    primary_decision = service.candidate_decisions[0]
    assert primary_decision.stage == "primary"
    assert primary_decision.state == "extraction_failed"
    assert primary_decision.rejection_reason == "no_extracted_text"


def test_gather_sources_records_successful_seed_url_as_primary(monkeypatch):
    class DummySearcher:
        def news_search(self, query: str, max_results: int = 10, time_range: str = "m"):
            return []

        def web_search(self, query: str, max_results: int = 10):
            return []

    monkeypatch.setattr(
        SourceAggregatorService, "_init_searcher", lambda self: DummySearcher()
    )

    def fake_extract_url(
        self, url: str, require_success: bool = False
    ) -> SourceCandidate:
        return SourceCandidate(
            url=url,
            domain="reuters.com",
            title="Seed story",
            published_date=None,
            author=None,
            full_text="President signed an executive order on AI safety. " * 8,
            extraction_error=None,
            bias_result=BiasResult(
                domain="reuters.com",
                bias=0,
                bias_label="Center",
                confidence=1.0,
                method="dataset",
                factual_rating="high",
                category="mainstream",
            ),
        )

    monkeypatch.setattr(SourceAggregatorService, "_extract_url", fake_extract_url)

    with patch("src.services.source_aggregator_service.settings") as mock_settings:
        mock_settings.retained_source_min = 1
        mock_settings.retained_source_max = 3
        mock_settings.candidate_probe_limit = 5
        mock_settings.rss_seed_fallback_enabled = False
        mock_settings.strict_bucket_enforcement = False
        mock_settings.required_bucket_groups = "center"
        mock_settings.analysis_rss_first_enabled = False
        service = SourceAggregatorService()
        sources = service.gather_sources(
            description="President signed an executive order on AI safety",
            url="https://reuters.com/seed",
        )

    assert len(sources) == 1
    primary_decision = service.candidate_decisions[0]
    assert primary_decision.stage == "primary"
    assert primary_decision.state == "retained"
    assert primary_decision.domain == "reuters.com"
    assert service.candidate_census().by_stage["primary"] == 1


def test_search_queries_round_robins_bucket_steps(monkeypatch):
    class DummySearcher:
        def __init__(self):
            self.queries = []

        def web_search(self, query: str, max_results: int = 10):
            self.queries.append(query)
            domain = query.split("site:", 1)[1].split(" ", 1)[0]
            return [
                SearchResult(
                    title=domain,
                    url=f"https://{domain}/story",
                    snippet="snippet",
                    source=domain,
                )
            ]

        def news_search(self, query: str, max_results: int = 10, time_range: str = "w"):
            return []

    searcher = DummySearcher()
    monkeypatch.setattr(
        SourceAggregatorService, "_init_searcher", lambda self: searcher
    )
    service = SourceAggregatorService()
    plan = SourcePlan(
        required_buckets=[
            BucketSpec(
                label="left_side",
                bias_values={-1},
                required=True,
                domain_targets=["left.example.com"],
                probe_quota=2,
                result_quota=1,
                exact_bias_order=[-1],
            ),
            BucketSpec(
                label="right_side",
                bias_values={1},
                required=True,
                domain_targets=["right.example.com"],
                probe_quota=2,
                result_quota=1,
                exact_bias_order=[1],
            ),
        ],
        optional_buckets=[],
        domain_targets_per_bucket={
            "left_side": ["left.example.com"],
            "right_side": ["right.example.com"],
        },
        search_plan=[
            {
                "phase": "site_search",
                "bucket": "left_side",
                "domains": ["left.example.com"],
                "required": True,
            },
            {
                "phase": "site_search",
                "bucket": "right_side",
                "domains": ["right.example.com"],
                "required": True,
            },
        ],
        bucket_probe_sequence=["right_side", "left_side"],
        proceed_minimum_groups=["left_side", "right_side"],
        target_unique_exact_biases=2,
        seed_bias=-1,
        seed_domain=None,
    )

    results = service._search_queries(
        [QueryAttempt(query="story", family="lexical", source="input")], plan
    )

    assert [result.source for result in results] == [
        "right.example.com",
        "left.example.com",
    ]


def test_build_query_attempts_prefers_story_packet_query_families():
    service = SourceAggregatorService()
    packet = StoryPacket(
        canonical_headline="James Comey indicted over X post",
        query_pack=["flat query"],
        query_families={
            "lexical": ["lexical query"],
            "semantic_paraphrase": ["semantic query"],
            "opposing_frame": ["opposing query"],
            "visual_social": ["visual query"],
        },
    )

    attempts = service._build_query_attempts(
        "fallback description",
        None,
        [],
        story_packet=packet,
    )

    # Query families should appear first, preserving family order
    query_strings = [a.query for a in attempts]
    assert query_strings[:4] == [
        "lexical query",
        "semantic query",
        "opposing query",
        "visual query",
    ]
    # Each attempt should carry its family tag
    assert attempts[0].family == "lexical"
    assert attempts[1].family == "semantic_paraphrase"
    assert attempts[2].family == "opposing_frame"
    assert attempts[3].family == "visual_social"


def test_build_query_attempts_preserves_more_than_four_queries_across_families():
    service = SourceAggregatorService()
    packet = StoryPacket(
        canonical_headline="High profile court ruling",
        query_pack=[],
        query_families={
            "lexical": [
                "lexical 1",
                "lexical 2",
                "lexical 3",
                "lexical 4",
                "lexical 5",
            ],
            "semantic_paraphrase": ["semantic 1", "semantic 2"],
            "opposing_frame": ["opposing 1"],
            "visual_social": ["visual 1"],
        },
    )

    attempts = service._build_query_attempts("", None, [], story_packet=packet)
    query_strings = [attempt.query for attempt in attempts]

    assert len(query_strings) > 4
    assert "lexical 5" not in query_strings
    assert {"semantic 1", "semantic 2", "opposing 1", "visual 1"}.issubset(
        set(query_strings)
    )


def test_build_query_attempts_dedupes_query_text_without_losing_later_families():
    service = SourceAggregatorService()
    packet = StoryPacket(
        canonical_headline="High profile court ruling",
        query_pack=[],
        query_families={
            "lexical": ["shared story query"],
            "semantic_paraphrase": ["shared story query", "unique semantic query"],
        },
    )

    attempts = service._build_query_attempts("", None, [], story_packet=packet)
    shared_attempts = [
        attempt for attempt in attempts if attempt.query == "shared story query"
    ]

    assert len(shared_attempts) == 1
    assert shared_attempts[0].family == "lexical"
    assert any(
        attempt.query == "unique semantic query"
        and attempt.family == "semantic_paraphrase"
        for attempt in attempts
    )


def test_search_queries_preserves_exact_bias_lane_order_inside_bucket(monkeypatch):
    class DummySearcher:
        def web_search(self, query: str, max_results: int = 10):
            domain = query.split("site:", 1)[1].split(" ", 1)[0]
            return [
                SearchResult(
                    title=domain,
                    url=f"https://{domain}/story",
                    snippet="snippet",
                    source=domain,
                )
            ]

        def news_search(self, query: str, max_results: int = 10, time_range: str = "w"):
            return []

    monkeypatch.setattr(
        SourceAggregatorService, "_init_searcher", lambda self: DummySearcher()
    )
    service = SourceAggregatorService()
    plan = SourcePlan(
        required_buckets=[
            BucketSpec(
                label="right_side",
                bias_values={2, 3},
                required=True,
                domain_targets=["lean-right.example.com", "right.example.com"],
                probe_quota=4,
                result_quota=2,
                exact_bias_order=[2, 3],
            ),
        ],
        optional_buckets=[],
        domain_targets_per_bucket={
            "right_side": ["lean-right.example.com", "right.example.com"],
        },
        search_plan=[
            {
                "phase": "site_search",
                "bucket": "right_side",
                "exact_bias": 2,
                "domains": ["lean-right.example.com"],
                "required": True,
            },
            {
                "phase": "site_search",
                "bucket": "right_side",
                "exact_bias": 3,
                "domains": ["right.example.com"],
                "required": True,
            },
        ],
        bucket_probe_sequence=["right_side"],
        proceed_minimum_groups=["right_side"],
        target_unique_exact_biases=2,
        seed_bias=-2,
        seed_domain=None,
    )

    results = service._search_queries(
        [QueryAttempt(query="story", family="lexical", source="input")], plan
    )

    assert [result.source for result in results] == [
        "lean-right.example.com",
        "right.example.com",
    ]


def test_candidate_census_persists_bucket_lane_attempts(monkeypatch):
    class DummySearcher:
        def web_search(self, query: str, max_results: int = 10):
            if "empty-right.example.com" in query:
                return []
            domain = query.split("site:", 1)[1].split(" ", 1)[0]
            return [
                SearchResult(
                    title=domain,
                    url=f"https://{domain}/story",
                    snippet="snippet",
                    source=domain,
                )
            ]

        def news_search(self, query: str, max_results: int = 10, time_range: str = "w"):
            return []

    monkeypatch.setattr(
        SourceAggregatorService, "_init_searcher", lambda self: DummySearcher()
    )
    service = SourceAggregatorService()
    plan = SourcePlan(
        required_buckets=[
            BucketSpec(
                label="right_side",
                bias_values={2},
                required=True,
                domain_targets=["empty-right.example.com"],
                probe_quota=2,
                result_quota=1,
                exact_bias_order=[2],
            ),
            BucketSpec(
                label="left_side",
                bias_values={-2},
                required=True,
                domain_targets=["left.example.com"],
                probe_quota=1,
                result_quota=1,
                exact_bias_order=[-2],
            ),
        ],
        optional_buckets=[],
        domain_targets_per_bucket={
            "right_side": ["empty-right.example.com"],
            "left_side": ["left.example.com"],
        },
        search_plan=[
            {
                "phase": "site_search",
                "bucket": "right_side",
                "exact_bias": 2,
                "domains": ["empty-right.example.com"],
                "required": True,
            },
            {
                "phase": "site_search",
                "bucket": "left_side",
                "exact_bias": -2,
                "domains": ["left.example.com"],
                "required": True,
            },
        ],
        bucket_probe_sequence=["right_side", "left_side"],
        proceed_minimum_groups=["right_side", "left_side"],
        target_unique_exact_biases=2,
        seed_bias=None,
        seed_domain=None,
    )

    results = service._search_queries(
        [QueryAttempt(query="story", family="lexical", source="input")], plan
    )
    attempts = service.candidate_census().bucket_lane_attempts

    assert [result.source for result in results] == ["left.example.com"]
    assert len(attempts) == 2
    assert attempts[0].bucket_label == "right_side"
    assert attempts[0].exact_bias == 2
    assert attempts[0].result_count == 0
    assert attempts[0].exhausted_reason == "no_results"
    assert attempts[0].query_family == "lexical"
    assert attempts[1].bucket_label == "left_side"
    assert attempts[1].new_result_count == 1
    assert attempts[1].query_family == "lexical"


def test_retained_selection_respects_bucket_result_quota():
    def candidate(domain: str, bias: int, bucket: str) -> SourceCandidate:
        return SourceCandidate(
            url=f"https://{domain}/story",
            domain=domain,
            title=f"{domain} story",
            published_date=None,
            author=None,
            full_text="story text" * 50,
            extraction_error=None,
            bias_result=BiasResult(
                domain=domain,
                bias=bias,
                bias_label=bucket,
                confidence=1.0,
                method="dataset",
                factual_rating="high",
                category="mainstream",
            ),
            bucket_label=bucket,
        )

    def score(source: SourceCandidate, total: float) -> ScoredCandidate:
        return ScoredCandidate(
            url=source.url,
            domain=source.domain,
            title=source.title,
            bias=source.bias_result.bias if source.bias_result else 0,
            bucket_label=source.bucket_label or "",
            total_score=total,
            event_similarity=1.0,
            similarity_score=0.25,
            bucket_need_score=0.30,
            novelty_score=0.15,
            factuality_score=0.15,
            freshness_score=0.10,
            duplicate_penalty=0.0,
        )

    left_one = candidate("left-one.example.com", -2, "left_side")
    left_two = candidate("left-two.example.com", -3, "left_side")
    right_one = candidate("right-one.example.com", 2, "right_side")
    plan = SourcePlan(
        required_buckets=[
            BucketSpec(
                label="left_side",
                bias_values={-2, -3},
                required=True,
                result_quota=1,
            ),
            BucketSpec(
                label="right_side",
                bias_values={2},
                required=True,
                result_quota=1,
            ),
        ],
        optional_buckets=[],
        domain_targets_per_bucket={},
        search_plan=[],
        bucket_probe_sequence=["left_side", "right_side"],
        proceed_minimum_groups=["left_side", "right_side"],
        target_unique_exact_biases=2,
        seed_bias=None,
        seed_domain=None,
    )
    service = SourceAggregatorService()
    service._candidate_decisions = [
        CandidateDecision(
            url=left_one.url,
            domain=left_one.domain,
            title=left_one.title,
            stage="site_search",
            state="extracted",
            bucket_label="left_side",
        ),
        CandidateDecision(
            url=left_two.url,
            domain=left_two.domain,
            title=left_two.title,
            stage="site_search",
            state="extracted",
            bucket_label="left_side",
        ),
        CandidateDecision(
            url=right_one.url,
            domain=right_one.domain,
            title=right_one.title,
            stage="site_search",
            state="extracted",
            bucket_label="right_side",
        ),
    ]
    sources: list[SourceCandidate] = []

    with patch("src.services.source_aggregator_service.settings") as mock_settings:
        mock_settings.retained_source_min = 2
        mock_settings.retained_source_max = 3
        mock_settings.max_per_exact_bias = 10
        mock_settings.max_per_bucket_group = 10
        mock_settings.allow_same_bias_backfill = True
        service._select_scored_candidates(
            [
                (score(left_one, 0.99), left_one),
                (score(left_two, 0.98), left_two),
                (score(right_one, 0.50), right_one),
            ],
            sources,
            set(),
            set(),
            plan,
        )

    assert [source.domain for source in sources] == [
        "left-one.example.com",
        "right-one.example.com",
    ]
    assert not service._candidate_allowed_by_policy(left_two, sources, plan)


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
    service._rss_retriever = NoopRssRetriever()
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


def test_preflight_adds_candidate_semantic_similarity(monkeypatch):
    class DummySemanticScorer:
        def __init__(self, story_packet, description):
            self.story_packet = story_packet
            self.description = description

        def score_candidate(self, candidate_title: str, candidate_text: str):
            return 0.91

        def score_candidate_diagnostics(
            self,
            candidate_title: str,
            candidate_text: str,
        ):
            class Scores:
                aggregate_similarity = 0.91
                title_similarity = 0.82
                lede_similarity = 0.88

            return Scores()

    monkeypatch.setattr(
        "src.services.source_aggregator_service.CandidateSemanticScorer",
        DummySemanticScorer,
    )

    def fake_extract_url(
        self, url: str, require_success: bool = False
    ) -> SourceCandidate:
        domain = urlparse(url).netloc.replace("www.", "")
        text = (
            "GOP senators voted to maintain Cuba sanctions and keep the embargo "
            "in place after a procedural challenge failed. "
        )
        return SourceCandidate(
            url=url,
            domain=domain,
            title="GOP senators vote to keep Cuba embargo",
            published_date=None,
            author=None,
            full_text=text * 8,
            extraction_error=None,
            bias_result=None,
        )

    monkeypatch.setattr(SourceAggregatorService, "_extract_url", fake_extract_url)

    story_packet = StoryPacket(
        canonical_headline="Senate Republicans reject Cuba blockade change",
        actors=["Senate Republicans"],
        action_verbs=["reject"],
        distinctive_terms=["Cuba"],
        must_have_terms=["Senate Republicans", "Cuba"],
        query_pack=["Senate Republicans Cuba blockade"],
    )

    service = SourceAggregatorService()
    plan = service._planner.plan(seed_bias=None, seed_domain=None)

    with patch("src.services.source_aggregator_service.settings") as mock_settings:
        mock_settings.candidate_probe_limit = 10
        mock_settings.semantic_candidate_scoring_enabled = True
        mock_settings.semantic_fail_open = True

        scored = service._preflight_search_results(
            results=[
                SearchResult(
                    title="GOP senators vote to keep Cuba embargo",
                    url="https://center.example.com/cuba",
                    snippet="same event different wording",
                    source="center",
                )
            ],
            description="Senate Republicans reject attempt to end Cuba blockade",
            sources=[],
            seen_urls=set(),
            seen_domains=set(),
            story_packet=story_packet,
            plan=plan,
        )

    assert len(scored) == 1
    candidate = scored[0][1]
    assert scored[0][0].event_similarity == 0.91
    assert candidate.semantic_similarity == 0.91
    assert candidate.semantic_title_similarity == 0.82
    assert candidate.semantic_lede_similarity == 0.88
    assert candidate.coverage_type == "direct"
    assert candidate.distinctive_term_overlap is not None
    assert (
        service.candidate_decisions[0].relevance_diagnostics[
            "semantic_title_similarity"
        ]
        == 0.82
    )


def test_preflight_prefetches_candidates_concurrently_preserving_order(monkeypatch):
    active = 0
    max_active = 0
    lock = Lock()

    def fake_extract_url(
        self, url: str, require_success: bool = False
    ) -> SourceCandidate:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1

        domain = urlparse(url).netloc.replace("www.", "")
        return SourceCandidate(
            url=url,
            domain=domain,
            title=domain,
            published_date=None,
            author=None,
            full_text="deterministic article text " * 30,
            extraction_error=None,
            bias_result=None,
        )

    monkeypatch.setattr(SourceAggregatorService, "_extract_url", fake_extract_url)

    service = SourceAggregatorService()
    plan = service._planner.plan(seed_bias=None, seed_domain=None)
    results = [
        SearchResult(
            title=f"Candidate {idx}",
            url=f"https://source{idx}.example.com/story",
            snippet="snippet",
            source=f"source{idx}",
        )
        for idx in range(4)
    ]

    with patch("src.services.source_aggregator_service.settings") as mock_settings:
        mock_settings.candidate_probe_limit = 4
        mock_settings.semantic_candidate_scoring_enabled = False

        started_at = time.perf_counter()
        scored = service._preflight_search_results(
            results=results,
            description="story description",
            sources=[],
            seen_urls=set(),
            seen_domains=set(),
            story_packet=None,
            plan=plan,
        )
        elapsed = time.perf_counter() - started_at

    assert elapsed < 0.16
    assert max_active > 1
    assert service._probed_count == 4
    assert [candidate.domain for _, candidate in scored] == [
        "source0.example.com",
        "source1.example.com",
        "source2.example.com",
        "source3.example.com",
    ]


def test_extract_keywords_reuses_keyword_extractor(monkeypatch):
    class FakeKeywordExtractor:
        instances = 0

        def __init__(self):
            type(self).instances += 1

        def extract(self, text: str, top_n: int = 10):
            return [SimpleNamespace(term="shared")]

    monkeypatch.setattr(
        "src.services.source_aggregator_service.KeywordExtractor",
        FakeKeywordExtractor,
    )

    service = SourceAggregatorService()

    assert service._extract_keywords("first story text") == ["shared"]
    assert service._extract_keywords("second story text") == ["shared"]
    assert FakeKeywordExtractor.instances == 1


def test_rss_plan_step_uses_story_matching_when_packet_available():
    calls = []

    class StoryAwareRss:
        def search_story(self, story_packet, bucket_spec, *, max_results: int = 8):
            calls.append(("search_story", story_packet, bucket_spec.label))
            return [
                SearchResult(
                    title="Matched RSS",
                    url="https://center.example.com/rss-story",
                    snippet="matched",
                    source="rss:Center",
                )
            ]

        def search(self, query: str, *, domains: list[str], max_results: int = 8):
            calls.append(("search", query, domains))
            return []

    service = SourceAggregatorService()
    service._rss_retriever = StoryAwareRss()
    packet = StoryPacket(canonical_headline="Jane Doe vetoes transit bill")
    bucket = BucketSpec(
        label="center",
        bias_values={0},
        required=False,
        domain_targets=["center.example.com"],
    )
    plan = SourcePlan(
        required_buckets=[],
        optional_buckets=[bucket],
        domain_targets_per_bucket={"center": ["center.example.com"]},
        search_plan=[],
        bucket_probe_sequence=["center"],
        proceed_minimum_groups=[],
        target_unique_exact_biases=1,
        seed_bias=None,
        seed_domain=None,
    )
    results = []

    with patch("src.services.source_aggregator_service.settings") as mock_settings:
        mock_settings.analysis_rss_first_enabled = True
        service._search_plan_step(
            "Jane Doe transit",
            {
                "phase": "rss",
                "bucket": "center",
                "domains": ["center.example.com"],
            },
            packet,
            plan,
            results.extend,
        )

    assert calls == [("search_story", packet, "center")]
    assert results[0].url == "https://center.example.com/rss-story"


def test_gather_sources_keeps_opposite_side_with_semantic_scores(monkeypatch):
    class DummySearcher:
        def news_search(self, query: str, max_results: int = 10, time_range: str = "w"):
            return [
                SearchResult(
                    title="Left source 1",
                    url="https://left1.example.com/cuba",
                    snippet="left",
                    source="left",
                ),
                SearchResult(
                    title="Left source 2",
                    url="https://left2.example.com/cuba",
                    snippet="left",
                    source="left",
                ),
                SearchResult(
                    title="Left source 3",
                    url="https://left3.example.com/cuba",
                    snippet="left",
                    source="left",
                ),
                SearchResult(
                    title="Left source 4",
                    url="https://left4.example.com/cuba",
                    snippet="left",
                    source="left",
                ),
                SearchResult(
                    title="Left source 5",
                    url="https://left5.example.com/cuba",
                    snippet="left",
                    source="left",
                ),
                SearchResult(
                    title="Center source",
                    url="https://center.example.com/cuba",
                    snippet="center",
                    source="center",
                ),
                SearchResult(
                    title="Right source uses different wording",
                    url="https://right.example.com/cuba",
                    snippet="right",
                    source="right",
                ),
            ]

        def web_search(self, query: str, max_results: int = 10):
            return []

    class DummySemanticScorer:
        def __init__(self, story_packet, description):
            self.story_packet = story_packet
            self.description = description

        def score_candidate(self, candidate_title: str, candidate_text: str):
            if "GOP senators" in candidate_text:
                return 0.92
            return 0.75

    bias_by_domain = {
        "left1.example.com": (-1, "Slight Left"),
        "left2.example.com": (-2, "Lean Left"),
        "left3.example.com": (-3, "Left"),
        "left4.example.com": (-4, "Far Left"),
        "left5.example.com": (-1, "Slight Left"),
        "center.example.com": (0, "Center"),
        "right.example.com": (2, "Lean Right"),
    }

    def fake_extract_url(
        self, url: str, require_success: bool = False
    ) -> SourceCandidate:
        domain = urlparse(url).netloc.replace("www.", "")
        bias_value, bias_label = bias_by_domain[domain]
        if domain == "right.example.com":
            title = "GOP senators keep Cuba embargo"
            text = (
                "GOP senators voted to maintain Cuba sanctions and keep the embargo "
                "in place after a procedural challenge failed. "
            )
        else:
            title = "Senate Republicans reject Cuba blockade change"
            text = (
                "Senate Republicans reject the Cuba blockade change after a vote "
                "on sanctions and trade restrictions. "
            )
        return SourceCandidate(
            url=url,
            domain=domain,
            title=title,
            published_date=None,
            author=None,
            full_text=text * 8,
            extraction_error=None,
            bias_result=BiasResult(
                domain=domain,
                bias=bias_value,
                bias_label=bias_label,
                confidence=1.0,
                method="dataset",
                factual_rating="high",
                category="mainstream",
            ),
        )

    monkeypatch.setattr(
        SourceAggregatorService, "_init_searcher", lambda self: DummySearcher()
    )
    monkeypatch.setattr(SourceAggregatorService, "_extract_url", fake_extract_url)
    monkeypatch.setattr(
        "src.services.source_aggregator_service.CandidateSemanticScorer",
        DummySemanticScorer,
    )

    story_packet = StoryPacket(
        canonical_headline="Senate Republicans reject Cuba blockade change",
        actors=["Senate Republicans"],
        action_verbs=["reject"],
        distinctive_terms=["Cuba"],
        must_have_terms=["Senate Republicans", "Cuba"],
        query_pack=["Senate Republicans Cuba blockade"],
    )

    service = SourceAggregatorService()
    service._rss_retriever = NoopRssRetriever()

    with patch("src.services.source_aggregator_service.settings") as mock_settings:
        mock_settings.retained_source_min = 3
        mock_settings.retained_source_max = 5
        mock_settings.candidate_probe_limit = 7
        mock_settings.search_time_window_days = 7
        mock_settings.strict_bucket_enforcement = True
        mock_settings.required_bucket_groups = "left_side,right_side"
        mock_settings.max_per_exact_bias = 1
        mock_settings.max_per_bucket_group = 2
        mock_settings.allow_same_bias_backfill = False
        mock_settings.analysis_rss_first_enabled = False
        mock_settings.semantic_candidate_scoring_enabled = True
        mock_settings.semantic_fail_open = True

        sources = service.gather_sources(
            description="Senate Republicans reject attempt to end Cuba blockade",
            url=None,
            story_packet=story_packet,
        )

    domains = {source.domain for source in sources}
    coverage = service.summarize_coverage(sources)

    assert "right.example.com" in domains
    assert coverage["coverage_satisfied"]
    assert coverage["right_count"] == 1
    assert coverage["left_count"] <= 2
    assert len(sources) <= 5


def test_candidate_census_explains_missing_bucket_from_failures():
    service = SourceAggregatorService()
    service._probed_count = 2
    service._candidate_decisions = [
        CandidateDecision(
            url="https://right.example.com/one",
            domain="right.example.com",
            title="Right story one",
            stage="site_search",
            state="extraction_failed",
            bucket_label="right_side",
            rejection_reason="no_extracted_text",
        ),
        CandidateDecision(
            url="https://right.example.com/two",
            domain="right.example.com",
            title="Right story two",
            stage="rss",
            state="extraction_failed",
            bucket_label="right_side",
            rejection_reason="extracted_text_too_short",
        ),
    ]

    with patch("src.services.source_aggregator_service.settings") as mock_settings:
        mock_settings.candidate_probe_limit = 2
        census = service.candidate_census(missing_buckets=["right_side"])

    explanation = census.missing_bucket_explanations[0]
    assert explanation.bucket_label == "right_side"
    assert explanation.reason == "all_candidates_failed_extraction"
    assert explanation.probed_count == 2
    assert explanation.by_state == {"extraction_failed": 2}
    assert explanation.rejection_reasons == {
        "no_extracted_text": 1,
        "extracted_text_too_short": 1,
    }
    assert explanation.probe_limit_reached


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
