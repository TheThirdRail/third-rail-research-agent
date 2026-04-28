import os

os.environ["DEBUG"] = "true"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.agents import profile_reader
from src.agents import config as agents_config
from src.core.config import settings
from src.database import session as db_session
from src.services.agent_config_service import AgentConfigService


class MockAgent:
    def __init__(self, role, goal, backstory, tools, llm, **kwargs):
        self.role = role
        self.llm = llm


@pytest.fixture()
def temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test_agent_flow.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}", raising=False)

    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(db_session, "engine", engine)
    monkeypatch.setattr(db_session, "SessionLocal", SessionLocal)

    db_session.init_db()
    yield
    engine.dispose()


def test_agent_config_flow(monkeypatch, temp_db):
    """Verify that agent configuration is loaded from DB and applied to Agent."""
    monkeypatch.setattr(profile_reader, "Agent", MockAgent)
    monkeypatch.setattr(
        profile_reader,
        "build_crewai_llm",
        lambda agent_name=None: "ollama/test-model-v1",
    )

    session = db_session.get_session()
    service = AgentConfigService(session)

    agent_name = "profile_reader"
    test_model = "ollama/test-model-v1"

    service.set_config(agent_name=agent_name, model=test_model, provider="ollama")

    agent = profile_reader.create_profile_reader_agent()

    assert "test-model-v1" in str(agent.llm), f"Expected 'test-model-v1' in {agent.llm}"

    session.close()


def test_agent_config_service_persists_reasoning_effort(temp_db):
    session = db_session.get_session()
    service = AgentConfigService(session)

    service.set_config(
        agent_name="profile_reader",
        provider="openai",
        model="gpt-5.4",
        reasoning_effort="high",
    )

    config = service.get_config("profile_reader")

    assert config is not None
    assert config.reasoning_effort == "high"

    service.set_config(
        agent_name="profile_reader",
        clear_reasoning_effort=True,
    )

    config = service.get_config("profile_reader")

    assert config is not None
    assert config.reasoning_effort is None

    session.close()
