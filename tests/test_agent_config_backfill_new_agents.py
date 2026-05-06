"""Agent configuration row creation and known-bad model backfill coverage."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.database.models import AgentConfiguration, Base
from src.database.session import (
    backfill_known_bad_agent_models,
    ensure_agent_config_rows,
)


def test_ensure_agent_config_rows_creates_missing_agents_from_template(tmp_path):
    db_path = tmp_path / "test_agent_backfill.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        session.add(
            AgentConfiguration(
                agent_name="fact_extractor",
                provider="groq",
                model="llama-3.3-70b-versatile",
                free_tier=True,
            )
        )
        session.commit()

    ensure_agent_config_rows(engine)

    with Session(engine) as session:
        rhetorical = (
            session.query(AgentConfiguration)
            .filter(AgentConfiguration.agent_name == "rhetorical_analyst")
            .first()
        )
        assert rhetorical is not None
        assert rhetorical.provider == "groq"
        assert rhetorical.model == "llama-3.3-70b-versatile"
        assert rhetorical.free_tier is True
        count_after_first = session.query(AgentConfiguration).count()

    ensure_agent_config_rows(engine)

    with Session(engine) as session:
        count_after_second = session.query(AgentConfiguration).count()

    assert count_after_second == count_after_first


def test_backfill_known_bad_agent_models_replaces_only_denylisted_rows(tmp_path):
    db_path = tmp_path / "test_known_bad_agent_backfill.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        session.add_all(
            [
                AgentConfiguration(
                    agent_name="fact_extractor",
                    provider="openrouter",
                    model="google/gemma-3n-e4b-it:free",
                    free_tier=True,
                ),
                AgentConfiguration(
                    agent_name="report_writer",
                    provider="groq",
                    model="llama-3.3-70b-versatile",
                    free_tier=False,
                ),
            ]
        )
        session.commit()

    backfill_known_bad_agent_models(engine)

    with Session(engine) as session:
        bad_row = (
            session.query(AgentConfiguration)
            .filter(AgentConfiguration.agent_name == "fact_extractor")
            .one()
        )
        valid_row = (
            session.query(AgentConfiguration)
            .filter(AgentConfiguration.agent_name == "report_writer")
            .one()
        )
        assert bad_row.provider == "openrouter"
        assert bad_row.model == "free"
        assert valid_row.provider == "groq"
        assert valid_row.model == "llama-3.3-70b-versatile"

    backfill_known_bad_agent_models(engine)

    with Session(engine) as session:
        bad_row = (
            session.query(AgentConfiguration)
            .filter(AgentConfiguration.agent_name == "fact_extractor")
            .one()
        )
        assert bad_row.model == "free"
