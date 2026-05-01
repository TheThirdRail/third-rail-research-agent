import os

os.environ["DEBUG"] = "true"

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from src.database.models import AgentConfiguration, Base
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
    assert "relevance_score" in source_columns
    assert "source_score" in source_columns
    assert "bucket_label" in source_columns
    assert "exact_bias" in source_columns
    assert "coverage_type" in source_columns
    assert "extractor_method" in source_columns
    assert "extraction_error" in source_columns
    assert "extraction_error_code" in source_columns
    assert "http_status" in source_columns
    assert "og_image_url" in source_columns
    assert "embedded_post_urls_json" in source_columns
    assert "image_alt_text_json" in source_columns
    assert "media_captions_json" in source_columns
    assert "relevance_diagnostics_json" in source_columns
    assert "media_diagnostics_json" in source_columns
    assert "key_framing" in source_columns
    assert "structured_claims" in analysis_columns
    assert "coverage_asymmetry" in analysis_columns
    assert "narrative_json" in analysis_columns
    assert "owner_user_id" in profile_columns
    assert "raw_content" in profile_columns
    assert "format" in profile_columns
    assert "parsed_json" in profile_columns
    assert "version" in profile_columns


def test_hardening_migration_syncs_diagnostic_tables_and_snapshots(tmp_path):
    db_path = tmp_path / "test_hardening_diagnostics.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE stories (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(
            text(
                "CREATE TABLE analyses ("
                "id VARCHAR(36) PRIMARY KEY, "
                "story_id VARCHAR(36) UNIQUE"
                ")"
            )
        )

    Base.metadata.create_all(bind=engine)
    ensure_hardening_schema(engine)
    ensure_hardening_schema(engine)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    analysis_columns = {col["name"] for col in inspector.get_columns("analyses")}
    analysis_run_columns = {
        col["name"] for col in inspector.get_columns("analysis_runs")
    }
    retrieval_candidate_columns = {
        col["name"] for col in inspector.get_columns("retrieval_candidates")
    }
    source_finding_columns = {
        col["name"] for col in inspector.get_columns("source_findings")
    }
    visual_evidence_columns = {
        col["name"] for col in inspector.get_columns("visual_evidence_records")
    }
    agent_finding_columns = {
        col["name"] for col in inspector.get_columns("agent_findings")
    }
    agent_handoff_columns = {
        col["name"] for col in inspector.get_columns("agent_handoffs")
    }

    assert "analysis_runs" in tables
    assert "retrieval_candidates" in tables
    assert "source_findings" in tables
    assert "visual_evidence_records" in tables
    assert "agent_findings" in tables
    assert "agent_handoffs" in tables
    assert "coverage_snapshot_json" in analysis_columns
    assert "candidate_census_json" in analysis_columns
    assert "visual_evidence_json" in analysis_columns
    assert "agent_handoff_snapshot_json" in analysis_columns
    assert {"status", "coverage_snapshot_json", "candidate_census_json"} <= (
        analysis_run_columns
    )
    assert {
        "analysis_run_id",
        "stage",
        "state",
        "bucket_label",
        "exact_bias",
        "relevance_diagnostics_json",
        "media_diagnostics_json",
    } <= retrieval_candidate_columns
    assert {
        "analysis_id",
        "source_id",
        "source_ref",
        "key_framing",
        "notable_claim",
        "evidence_snippet",
    } <= source_finding_columns
    assert {
        "analysis_id",
        "source_id",
        "source_url",
        "media_url",
        "observable_text",
        "visible_symbols_or_numbers_json",
    } <= visual_evidence_columns
    assert {
        "analysis_id",
        "agent_name",
        "finding_type",
        "finding_text",
        "source_refs_json",
    } <= agent_finding_columns
    assert {
        "analysis_id",
        "stage",
        "from_agent",
        "to_agent",
        "summary",
        "payload_json",
    } <= agent_handoff_columns


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
