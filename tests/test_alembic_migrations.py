from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from src.database.session import get_alembic_revision_status


def _alembic_config(db_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def test_alembic_upgrade_creates_current_schema(tmp_path):
    db_path = tmp_path / "fresh.db"

    command.upgrade(_alembic_config(db_path), "head")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    assert "alembic_version" in tables
    assert "stories" in tables
    assert "analysis_runs" in tables
    assert "retrieval_candidates" in tables
    assert "semantic_documents" in tables
    assert "semantic_chunks" in tables
    assert "source_findings" in tables
    assert "visual_evidence_records" in tables
    assert "agent_findings" in tables
    assert "agent_handoffs" in tables

    analysis_columns = {col["name"] for col in inspector.get_columns("analyses")}
    assert "coverage_snapshot_json" in analysis_columns
    assert "candidate_census_json" in analysis_columns
    assert "visual_evidence_json" in analysis_columns
    assert "report_validation_warnings_json" in analysis_columns

    status, detail = get_alembic_revision_status(f"sqlite:///{db_path}")
    assert status == "ok"
    assert "head" in detail


def test_alembic_upgrade_syncs_legacy_sqlite_schema(tmp_path):
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE stories (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE sources (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(
            text(
                "CREATE TABLE analyses ("
                "id VARCHAR(36) PRIMARY KEY, "
                "story_id VARCHAR(36) UNIQUE"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE agent_configurations (agent_name VARCHAR(50) PRIMARY KEY)"
            )
        )

    engine.dispose()
    command.upgrade(_alembic_config(db_path), "head")

    upgraded_engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(upgraded_engine)
    tables = set(inspector.get_table_names())
    story_columns = {col["name"] for col in inspector.get_columns("stories")}
    source_columns = {col["name"] for col in inspector.get_columns("sources")}
    analysis_columns = {col["name"] for col in inspector.get_columns("analyses")}
    analysis_run_columns = {
        col["name"] for col in inspector.get_columns("analysis_runs")
    }
    agent_config_columns = {
        col["name"] for col in inspector.get_columns("agent_configurations")
    }

    assert "analysis_runs" in tables
    assert "retrieval_candidates" in tables
    assert "parsed_metadata" in story_columns
    assert "bucket_label" in source_columns
    assert "coverage_snapshot_json" in analysis_columns
    assert "report_validation_warnings_json" in analysis_columns
    assert "report_validation_warnings_json" in analysis_run_columns
    assert "free_tier" in agent_config_columns
    assert "reasoning_effort" in agent_config_columns


def test_alembic_revision_status_warns_when_database_is_unstamped(tmp_path):
    db_path = tmp_path / "unstamped.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE stories (id VARCHAR(36) PRIMARY KEY)"))
    engine.dispose()

    status, detail = get_alembic_revision_status(f"sqlite:///{db_path}")

    assert status == "warn"
    assert "not stamped" in detail
