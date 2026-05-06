"""Query-family scheduler coverage for planned retrieval lanes."""

from src.schemas.story_packet import StoryPacket
from src.services.balanced_source_planner import BucketSpec, SourcePlan
from src.services.source_aggregator_service import QueryAttempt, SourceAggregatorService


def test_visual_social_query_family_gets_actual_search_attempt(monkeypatch):
    class DummySearcher:
        def __init__(self):
            self.queries = []

        def news_search(self, query: str, max_results: int = 10, time_range: str = "w"):
            self.queries.append(query)
            return []

        def web_search(self, query: str, max_results: int = 10):
            self.queries.append(query)
            return []

    searcher = DummySearcher()
    monkeypatch.setattr(
        SourceAggregatorService,
        "_init_searcher",
        lambda self: searcher,
    )
    service = SourceAggregatorService()
    packet = StoryPacket(
        canonical_headline="Example Person posts 8647 image on X",
        query_pack=[],
        query_families={"visual_social": ["Example Person 8647 X"]},
    )
    plan = SourcePlan(
        required_buckets=[
            BucketSpec(
                label="right_side",
                bias_values={2},
                required=True,
                probe_quota=2,
                result_quota=1,
            )
        ],
        optional_buckets=[],
        domain_targets_per_bucket={"right_side": []},
        search_plan=[
            {
                "phase": "open_web",
                "bucket": "right_side",
                "domains": [],
                "required": True,
            }
        ],
        bucket_probe_sequence=["right_side"],
        proceed_minimum_groups=["right_side"],
        target_unique_exact_biases=1,
        seed_bias=None,
        seed_domain=None,
    )

    service._search_queries(
        [
            QueryAttempt(
                query="Example Person 8647 X",
                family="visual_social",
                source="story_packet",
            )
        ],
        plan,
        packet,
    )

    assert "Example Person 8647 X" in searcher.queries
    attempts = service.candidate_census().bucket_lane_attempts
    assert attempts
    assert attempts[0].query_family == "visual_social"
    assert attempts[0].stage == "open_web"
