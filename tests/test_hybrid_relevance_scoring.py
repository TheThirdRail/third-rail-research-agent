from datetime import UTC, datetime

from src.schemas.story_packet import StoryPacket
from src.services.candidate_semantic_scorer import CandidateSemanticScorer
from src.services.relevance_scorer_service import RelevanceScorerService


class KeywordEmbeddingProvider:
    provider_name = "keyword"
    model_name = "keyword-v1"
    dimensions = 2

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        lowered = text.lower()
        if "cuba" in lowered and (
            "sanctions" in lowered or "embargo" in lowered or "blockade" in lowered
        ):
            return [1.0, 0.0]
        return [0.0, 1.0]


def test_candidate_semantic_scorer_reports_chunk_similarity():
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
        embedding_provider=KeywordEmbeddingProvider(),
    )

    scores = scorer.score_candidate_diagnostics(
        "Procedural vote in Senate",
        (
            "The story begins with procedural detail. "
            * 30
            + "GOP senators voted to maintain Cuba sanctions and keep the embargo "
            "in place after a procedural challenge failed."
        ),
    )

    assert scores.chunk_similarity == 1.0
    assert scores.aggregate_similarity == 1.0


def test_relevance_accepts_same_event_from_semantic_chunk_similarity():
    packet = StoryPacket(
        canonical_headline="Senate Republicans reject Cuba blockade change",
        actors=["Senate Republicans"],
        action_verbs=["reject"],
        distinctive_terms=["Cuba"],
        must_have_terms=["Senate Republicans", "Cuba"],
        query_pack=["Senate Republicans Cuba blockade"],
    )

    result = RelevanceScorerService().score(
        candidate_title="GOP senators vote to keep Cuba embargo",
        candidate_text=(
            "GOP senators voted to maintain Cuba sanctions and keep the embargo "
            "in place after a procedural challenge failed."
        ),
        candidate_date=None,
        story_packet=packet,
        semantic_similarity=0.2,
        semantic_chunk_similarity=0.91,
    )

    assert result.coverage_type == "direct"
    assert result.rejection_reason is None
    assert result.semantic_similarity == 0.91
    assert result.semantic_chunk_similarity == 0.91


def test_relevance_reports_explicit_wrong_event_diagnostic():
    packet = StoryPacket(
        canonical_headline="James Comey indicted over X post showing 8647",
        actors=["James Comey"],
        action_verbs=["indicted"],
        distinctive_terms=["8647"],
        must_have_terms=["James Comey", "indicted", "8647"],
        query_pack=["James Comey 8647"],
    )

    result = RelevanceScorerService().score(
        candidate_title="James Comey comments on unrelated hearing",
        candidate_text=(
            "James Comey commented on a congressional hearing and broader legal "
            "politics. The article did not discuss an indictment."
        ),
        candidate_date=None,
        story_packet=packet,
    )

    assert result.rejection_reason == "same_person_wrong_event"
    assert result.to_diagnostics().rejection_reason == "same_person_wrong_event"


def test_relevance_time_overlap_normalizes_aware_candidate_date():
    packet = StoryPacket(
        canonical_headline="Senate Republicans reject Cuba blockade change",
        time_window_start=datetime(2026, 5, 11, 8, 0, 0),
        time_window_end=datetime(2026, 5, 19, 8, 0, 0),
    )

    result = RelevanceScorerService()._time_overlap(
        datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC),
        packet,
    )

    assert result == 1.0
