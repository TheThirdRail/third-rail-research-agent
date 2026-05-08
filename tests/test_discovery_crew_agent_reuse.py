from types import SimpleNamespace

import src.crews.discovery_crew as discovery_crew


def _fake_task(**kwargs):
    return SimpleNamespace(**kwargs)


def test_discovery_tasks_reuse_one_news_agent(monkeypatch):
    calls = []

    def fake_agent():
        agent = SimpleNamespace(name=f"news-{len(calls)}")
        calls.append(agent)
        return agent

    monkeypatch.setattr(discovery_crew, "Task", _fake_task)
    monkeypatch.setattr(discovery_crew, "create_news_aggregator_agent", fake_agent)

    tasks = discovery_crew.create_discovery_tasks(["law"], count=2)

    assert len(calls) == 1
    assert tasks[0].agent is calls[0]
    assert tasks[1].agent is calls[0]


def test_run_discovery_reuses_task_agent_in_crew(monkeypatch):
    calls = []
    captured = {}

    def fake_agent():
        agent = SimpleNamespace(name=f"news-{len(calls)}")
        calls.append(agent)
        return agent

    class FakeCrew:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def kickoff(self):
            return "discovery output"

    monkeypatch.setattr(discovery_crew, "Task", _fake_task)
    monkeypatch.setattr(discovery_crew, "Crew", FakeCrew)
    monkeypatch.setattr(discovery_crew, "create_news_aggregator_agent", fake_agent)

    result = discovery_crew.run_discovery(["law"], count=2)

    assert result["raw_output"] == "discovery output"
    assert len(calls) == 1
    assert captured["agents"] == [calls[0]]
    assert all(task.agent is calls[0] for task in captured["tasks"])
