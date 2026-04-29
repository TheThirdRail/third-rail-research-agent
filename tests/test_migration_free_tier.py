import os

os.environ["DEBUG"] = "true"

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from src.database.models import AgentConfiguration
from src.database.session import (
    backfill_agent_config_models,
    ensure_agent_config_schema,
    ensure_hardening_schema,
)


def test_free_tier_migration_adds_column(tmp_path):
    db_path = tmp_path / "test_free_tier.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE agent_configurations (agent_name VARCHAR(50) PRIMARY KEY)"
            )
        )

    ensure_agent_config_schema(engine)

    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("agent_configurations")}

    assert "free_tier" in columns
    assert "reasoning_effort" in columns


def test_hardening_migration_adds_existing_table_columns(tmp_path):
    db_path = tmp_path / "test_hardening_columns.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE stories (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE sources (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE analyses (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE channel_profiles (id VARCHAR(36) PRIMARY KEY)"))

    ensure_hardening_schema(engine)
    ensure_hardening_schema(engine)

    inspector = inspect(engine)
    story_columns = {col["name"] for col in inspector.get_columns("stories")}
    source_columns = {col["name"] for col in inspector.get_columns("sources")}
    analysis_columns = {col["name"] for col in inspector.get_columns("analyses")}
    profile_columns = {col["name"] for col in inspector.get_columns("channel_profiles")}

    assert "parsed_metadata" in story_columns
    assert "bias_provenance" in source_columns
    assert "is_curated_source" in source_columns
    assert "bias_category" in source_columns
    assert "structured_claims" in analysis_columns
    assert "coverage_asymmetry" in analysis_columns
    assert "narrative_json" in analysis_columns
    assert "owner_user_id" in profile_columns
    assert "raw_content" in profile_columns
    assert "format" in profile_columns
    assert "parsed_json" in profile_columns
    assert "version" in profile_columns


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
