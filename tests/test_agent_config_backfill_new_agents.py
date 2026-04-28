from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.database.models import AgentConfiguration, Base
from src.database.session import ensure_agent_config_rows


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
