from src.schemas.story_packet import StoryPacket
from src.services import story_parser_service
from src.services.relevance_scorer_service import RelevanceScorerService
from src.services.semantic_query_expansion_service import SemanticQueryExpansionService
from src.services.story_parser_service import StoryParserService


def test_story_parser_extracts_distinctive_visual_tokens():
    packet = StoryParserService().parse(
        "James Comey was indicted over an X post showing seashells arranged as 8647."
    )

    assert "8647" in packet.distinctive_terms
    assert "X" in packet.distinctive_terms
    assert "8647" in packet.number_markers
    assert "X" in packet.platform_markers
    assert any("shell" in term for term in packet.visual_descriptors)
    assert "8647" in packet.must_have_terms


def test_story_parser_populates_aliases_and_negative_disambiguators():
    packet = StoryParserService().parse(
        "Senate Republicans reject attempt to end Trump's blockade of Cuba; "
        "not about a budget proposal or unrelated border vote."
    )

    assert "GOP senators" in packet.aliases
    assert "Republicans" in packet.aliases
    assert "Trump" in packet.aliases
    assert any("budget proposal" in term for term in packet.negative_clues)
    assert packet.must_not_have_terms == packet.negative_clues


def test_story_parser_extracts_quote_number_and_platform_markers_from_seed_url():
    packet = StoryParserService().parse(
        'Officials debate whether "8647" in Comey seashell image was a threat.',
        seed_url="https://x.com/example/status/123",
    )

    assert "8647" in packet.quote_markers
    assert "8647" in packet.number_markers
    assert "X" in packet.platform_markers
    assert "8647" in packet.distinctive_terms
    assert "X" in packet.distinctive_terms


def test_story_parser_uses_seed_article_context_before_search_queries():
    packet = StoryParserService().parse(
        "Find other coverage of the linked article.",
        seed_url="https://example.com/politics/jane-smith-school-funding",
        seed_title="Senator Jane Smith vetoes school funding bill",
        seed_text=(
            'Senator Jane Smith vetoed the school funding bill after calling '
            'the AB123 formula "unworkable" during a press conference.'
        ),
    )

    assert packet.canonical_headline == "Senator Jane Smith vetoes school funding bill"
    assert "Senator Jane Smith" in packet.actors
    assert "vetoed" in packet.action_verbs
    assert "AB123" in packet.number_markers
    assert any(
        "Senator Jane Smith vetoes school funding bill" in query
        for query in packet.query_pack
    )


def test_story_parser_builds_query_families_for_bucket_lanes():
    packet = StoryParserService().parse(
        "James Comey was indicted over an X post showing seashells arranged as 8647."
    )

    assert "lexical" in packet.query_families
    assert "semantic_paraphrase" in packet.query_families
    assert "opposing_frame" in packet.query_families
    assert "visual_social" in packet.query_families
    assert any("8647" in query for query in packet.query_families["visual_social"])

    flattened = SemanticQueryExpansionService().flatten(packet.query_families)
    assert flattened
    assert flattened[0] in packet.query_families["lexical"]
    assert packet.query_expansion_diagnostics["source"] == "current_story_only"
    assert packet.query_expansion_diagnostics["deterministic_used"] is True


def test_story_parser_deterministic_expansion_uses_current_story_markers():
    packet = StoryParserService().parse(
        "James Comey was indicted over an X post showing seashells arranged as 8647."
    )

    semantic_queries = packet.query_families["semantic_paraphrase"]

    assert any("Comey" in query and "8647" in query for query in semantic_queries)
    assert any("Comey" in query and "indicted" in query for query in semantic_queries)


def test_story_parser_semantic_query_expansion_disabled_by_default(monkeypatch):
    def fail_get_router(*args, **kwargs):
        raise AssertionError("router should not be called when expansion is disabled")

    monkeypatch.setattr(
        story_parser_service.settings,
        "semantic_query_expansion_enabled",
        False,
        raising=False,
    )
    monkeypatch.setattr(story_parser_service, "get_llm_router", fail_get_router)

    packet = StoryParserService().parse(
        "Senate Republicans reject attempt to end Trump's blockade of Cuba"
    )

    assert packet.query_pack
    assert all("embargo vote" not in query for query in packet.query_pack)


def test_story_parser_semantic_query_expansion_appends_valid_queries(monkeypatch):
    class DummyRouter:
        def complete(self, messages, temperature=None, max_tokens=None):
            return """
            {
              "queries": [
                "Senate Republicans Cuba embargo vote",
                "GOP senators block Cuba trade concessions",
                "Republicans uphold Trump Cuba sanctions",
                "https://example.com/not-a-query",
                "too short"
              ],
              "aliases": ["Cuba embargo", "Cuba sanctions"]
            }
            """

    monkeypatch.setattr(
        story_parser_service.settings,
        "semantic_query_expansion_enabled",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        story_parser_service.settings,
        "semantic_query_expansion_max_queries",
        4,
        raising=False,
    )
    monkeypatch.setattr(
        story_parser_service.settings,
        "semantic_query_expansion_agent_name",
        "semantic_query_expander",
        raising=False,
    )
    monkeypatch.setattr(
        story_parser_service,
        "get_llm_router",
        lambda agent_name=None: DummyRouter(),
    )

    packet = StoryParserService().parse(
        "Senate Republicans reject attempt to end Trump's blockade of Cuba"
    )

    assert "Senate Republicans Cuba embargo vote" in packet.query_pack
    assert "GOP senators block Cuba trade concessions" in packet.query_pack
    assert "Republicans uphold Trump Cuba sanctions" in packet.query_pack
    assert all("https://" not in query for query in packet.query_pack)
    assert "Cuba embargo" in packet.aliases
    assert packet.query_expansion_diagnostics["llm_status"] == "expanded"
    assert packet.query_expansion_diagnostics["llm_added_count"] == 3


def test_story_parser_semantic_query_expansion_rejects_unanchored_queries(monkeypatch):
    class DummyRouter:
        def complete(self, messages, temperature=None, max_tokens=None):
            joined = "\n".join(message["content"] for message in messages)
            assert "previous quer" not in joined.lower()
            return """
            {
              "queries": [
                "unrelated healthcare budget fight",
                "Senate Republicans Cuba embargo vote"
              ],
              "aliases": []
            }
            """

    monkeypatch.setattr(
        story_parser_service.settings,
        "semantic_query_expansion_enabled",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        story_parser_service,
        "get_llm_router",
        lambda agent_name=None: DummyRouter(),
    )

    packet = StoryParserService().parse(
        "Senate Republicans reject attempt to end Trump's blockade of Cuba"
    )

    assert "Senate Republicans Cuba embargo vote" in packet.query_pack
    assert "unrelated healthcare budget fight" not in packet.query_pack
    assert packet.query_expansion_diagnostics["llm_rejected_count"] == 1


def test_story_parser_semantic_query_expansion_fails_open(monkeypatch):
    class FailingRouter:
        def complete(self, messages, temperature=None, max_tokens=None):
            raise RuntimeError("model unavailable")

    monkeypatch.setattr(
        story_parser_service.settings,
        "semantic_query_expansion_enabled",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        story_parser_service,
        "get_llm_router",
        lambda agent_name=None: FailingRouter(),
    )

    packet = StoryParserService().parse(
        "Senate Republicans reject attempt to end Trump's blockade of Cuba"
    )

    assert packet.query_pack
    assert all("embargo vote" not in query for query in packet.query_pack)


def test_story_parser_semantic_query_expansion_invalid_json_fails_open(monkeypatch):
    class BadJsonRouter:
        def complete(self, messages, temperature=None, max_tokens=None):
            return "not json"

    monkeypatch.setattr(
        story_parser_service.settings,
        "semantic_query_expansion_enabled",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        story_parser_service,
        "get_llm_router",
        lambda agent_name=None: BadJsonRouter(),
    )

    packet = StoryParserService().parse(
        "Senate Republicans reject attempt to end Trump's blockade of Cuba"
    )

    assert packet.query_pack
    assert all("embargo vote" not in query for query in packet.query_pack)


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


def test_relevance_accepts_same_event_different_wording_with_semantic_similarity():
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
        semantic_similarity=0.91,
    )

    assert result.coverage_type == "direct"
    assert result.rejection_reason is None
    assert result.semantic_similarity == 0.91
    assert result.distinctive_term_overlap > 0


def test_relevance_semantic_similarity_does_not_make_missing_marker_direct():
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
        candidate_title="James Comey indicted over X post",
        candidate_text=(
            "James Comey was indicted after officials reviewed an X post "
            "showing seashells, according to people familiar with the case."
        ),
        candidate_date=None,
        story_packet=packet,
        semantic_similarity=0.95,
    )

    assert result.coverage_type == "contextual"
    assert result.rejection_reason is not None


def test_relevance_semantic_similarity_does_not_override_must_not_have():
    packet = StoryPacket(
        canonical_headline="Governor vetoes transit bill",
        actors=["Governor Jane Doe"],
        action_verbs=["vetoes"],
        distinctive_terms=["transit bill"],
        must_have_terms=["Governor Jane Doe", "transit bill"],
        must_not_have_terms=["budget proposal"],
        query_pack=["Governor Jane Doe transit bill"],
    )

    result = RelevanceScorerService().score(
        candidate_title="Governor Jane Doe vetoes budget proposal",
        candidate_text=(
            "Governor Jane Doe vetoes a budget proposal after lawmakers "
            "debated transit spending."
        ),
        candidate_date=None,
        story_packet=packet,
        semantic_similarity=0.99,
    )

    assert result.rejection_reason == (
        "contains_disambiguation_exclusion: budget proposal"
    )


def test_relevance_semantic_similarity_does_not_override_must_have_failure():
    packet = StoryPacket(
        canonical_headline="Governor Jane Doe signs California tax bill",
        actors=["Governor Jane Doe"],
        action_verbs=["signs"],
        distinctive_terms=[],
        must_have_terms=["Governor Jane Doe", "California tax bill"],
        query_pack=["Governor Jane Doe California tax bill"],
    )

    result = RelevanceScorerService().score(
        candidate_title="Governor Jane Doe signs unrelated education order",
        candidate_text=(
            "Governor Jane Doe signed an education order after a school board "
            "meeting, according to state officials."
        ),
        candidate_date=None,
        story_packet=packet,
        semantic_similarity=0.99,
    )

    assert result.coverage_type != "direct"
    assert result.rejection_reason is not None


def test_relevance_score_returns_persistable_diagnostics():
    packet = StoryPacket(
        canonical_headline="James Comey indicted over X post showing 8647",
        actors=["James Comey"],
        action_verbs=["indicted"],
        distinctive_terms=["8647", "X"],
        must_have_terms=["James Comey", "indicted", "8647"],
        query_pack=["James Comey 8647"],
    )

    result = RelevanceScorerService().score(
        candidate_title="James Comey indicted over X post showing 8647",
        candidate_text="James Comey was indicted after an X post showed 8647.",
        candidate_date=None,
        story_packet=packet,
    )

    diagnostics = result.to_diagnostics()
    assert diagnostics.total == result.total
    assert diagnostics.coverage_type == "direct"
    assert diagnostics.model_dump(mode="json")["direct_evidence_score"] == (
        result.direct_evidence_score
    )
