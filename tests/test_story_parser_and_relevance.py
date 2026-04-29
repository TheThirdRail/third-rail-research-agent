from src.schemas.story_packet import StoryPacket
from src.services.relevance_scorer_service import RelevanceScorerService
from src.services.story_parser_service import StoryParserService


def test_story_parser_extracts_distinctive_visual_tokens():
    packet = StoryParserService().parse(
        "James Comey was indicted over an X post showing seashells arranged as 8647."
    )

    assert "8647" in packet.distinctive_terms
    assert "X" in packet.distinctive_terms
    assert any("shell" in term for term in packet.visual_descriptors)
    assert "8647" in packet.must_have_terms


def test_relevance_rejects_contextual_same_person_wrong_event():
    packet = StoryPacket(
        canonical_headline="James Comey indicted over X post showing 8647",
        actors=["James Comey"],
        action_verbs=["indicted"],
        distinctive_terms=["8647", "X"],
        visual_descriptors=["post", "seashell"],
        must_have_terms=["James Comey", "indicted", "8647"],
        query_pack=["James Comey 8647"],
    )

    result = RelevanceScorerService().score(
        candidate_title="John Bolton indictment called a warning",
        candidate_text=(
            "A commentary article mentions James Comey while discussing a separate "
            "John Bolton case and broader Trump administration legal fights."
        ),
        candidate_date=None,
        story_packet=packet,
    )

    assert result.coverage_type == "contextual"
    assert result.rejection_reason is not None


def test_relevance_accepts_direct_coverage_with_core_markers():
    packet = StoryPacket(
        canonical_headline="James Comey indicted over X post showing 8647",
        actors=["James Comey"],
        action_verbs=["indicted"],
        distinctive_terms=["8647", "X"],
        visual_descriptors=["post", "seashell"],
        must_have_terms=["James Comey", "indicted", "8647"],
        query_pack=["James Comey 8647"],
    )

    result = RelevanceScorerService().score(
        candidate_title="James Comey indicted over X post officials say showed 8647",
        candidate_text=(
            "James Comey was indicted after officials said his X post included "
            "seashells arranged to show 8647."
        ),
        candidate_date=None,
        story_packet=packet,
    )

    assert result.coverage_type == "direct"
    assert result.rejection_reason is None
