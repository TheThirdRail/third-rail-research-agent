from types import SimpleNamespace

from src.agents.source_aggregator import create_source_aggregator_agent


def fake_agent(**kwargs):
    return SimpleNamespace(**kwargs)


def test_prefetched_mode_disables_external_search_tools(monkeypatch):
    monkeypatch.setattr("src.agents.source_aggregator.Agent", fake_agent)
    monkeypatch.setattr(
        "src.agents.source_aggregator.build_crewai_llm", lambda **kwargs: None
    )
    agent = create_source_aggregator_agent(prefetched_mode=True)

    assert agent.tools == []


def test_exploratory_mode_keeps_search_tools(monkeypatch):
    monkeypatch.setattr("src.agents.source_aggregator.Agent", fake_agent)
    monkeypatch.setattr(
        "src.agents.source_aggregator.build_crewai_llm", lambda **kwargs: None
    )
    agent = create_source_aggregator_agent(prefetched_mode=False)

    tool_names = {tool.name for tool in agent.tools}
    assert "Web Search" in tool_names
    assert "Article Extractor" in tool_names
