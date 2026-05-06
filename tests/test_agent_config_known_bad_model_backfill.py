"""Focused tests for known-bad persisted agent model health visibility."""

from sqlalchemy.orm import Session

from src.cli import main as cli_main
from src.database import session as db_session
from src.database.models import AgentConfiguration


def _insert_agent_model(engine, *, agent_name: str, model: str) -> None:
    with Session(engine) as session:
        session.add(
            AgentConfiguration(
                agent_name=agent_name,
                provider="openrouter",
                model=model,
                free_tier=True,
            )
        )
        session.commit()


def test_known_bad_agent_model_rows_reports_clean_db(
    monkeypatch,
    temp_database_engine,
):
    monkeypatch.setattr(db_session, "engine", temp_database_engine)

    assert cli_main._known_bad_agent_model_rows() == []


def test_known_bad_agent_model_rows_reports_denylisted_model(
    monkeypatch,
    temp_database_engine,
):
    monkeypatch.setattr(db_session, "engine", temp_database_engine)
    _insert_agent_model(
        temp_database_engine,
        agent_name="source_aggregator",
        model="google/gemma-3n-e4b-it:free",
    )

    rows = cli_main._known_bad_agent_model_rows()

    assert rows == [
        "source_aggregator uses known-bad model google/gemma-3n-e4b-it:free"
    ]


def test_health_rows_warns_for_known_bad_agent_model(
    monkeypatch,
    temp_database_engine,
):
    monkeypatch.setattr(db_session, "engine", temp_database_engine)
    monkeypatch.setattr(
        cli_main,
        "get_alembic_revision_status",
        lambda: ("ok", "Database is at Alembic head."),
    )
    monkeypatch.setattr(cli_main.settings, "llm_provider", "lmstudio")
    monkeypatch.setattr(cli_main.settings, "embedding_provider", "fake")
    monkeypatch.setattr(cli_main.settings, "semantic_memory_enabled", False)
    monkeypatch.setattr(cli_main.settings, "semantic_candidate_scoring_enabled", False)
    monkeypatch.setattr(cli_main.settings, "semantic_vector_store", "none")
    monkeypatch.setattr(cli_main.settings, "screenshot_capture_enabled", False)
    monkeypatch.setattr(cli_main.settings, "screenshot_ocr_enabled", False)
    monkeypatch.setattr(
        type(cli_main.settings),
        "validate_feature_dependencies",
        lambda self: [],
    )
    _insert_agent_model(
        temp_database_engine,
        agent_name="source_aggregator",
        model="google/gemma-3n-e4b-it:free",
    )

    row = next(row for row in cli_main._health_rows() if row[0] == "Agent models")

    assert row[1] == "warn"
    assert "source_aggregator" in row[2]
    assert "google/gemma-3n-e4b-it:free" in row[2]
    assert row[3] == "Run `research-agent init`."
    assert "api_key" not in row[2].lower()
    assert "secret" not in row[2].lower()
