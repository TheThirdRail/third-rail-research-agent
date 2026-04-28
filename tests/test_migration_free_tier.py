import os

os.environ["DEBUG"] = "true"

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from src.database.models import AgentConfiguration
from src.database.session import backfill_agent_config_models, ensure_agent_config_schema


def test_free_tier_migration_adds_column(tmp_path):
    db_path = tmp_path / "test_free_tier.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE agent_configurations "
                "(agent_name VARCHAR(50) PRIMARY KEY)"
            )
        )

    ensure_agent_config_schema(engine)

    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("agent_configurations")}

    assert "free_tier" in columns
    assert "reasoning_effort" in columns


def test_backfill_normalizes_gemini_model_ids(tmp_path):
    db_path = tmp_path / "test_model_backfill.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE agent_configurations ("
                "agent_name VARCHAR(50) PRIMARY KEY, "
                "provider VARCHAR(50), "
                "model VARCHAR(100), "
                "temperature FLOAT, "
                "budget_limit FLOAT, "
                "free_tier BOOLEAN DEFAULT 0, "
                "reasoning_effort VARCHAR(20), "
                "created_at DATETIME, "
                "updated_at DATETIME"
                ")"
            )
        )

    with Session(engine) as session:
        session.add(
            AgentConfiguration(
                agent_name="bias_classifier",
                provider="gemini",
                model="models/gemini-2.0-flash",
                free_tier=True,
            )
        )
        session.commit()

    backfill_agent_config_models(engine)
    backfill_agent_config_models(engine)

    with Session(engine) as session:
        row = (
            session.query(AgentConfiguration)
            .filter(AgentConfiguration.agent_name == "bias_classifier")
            .first()
        )
        assert row is not None
        assert row.model == "gemini-2.0-flash"
