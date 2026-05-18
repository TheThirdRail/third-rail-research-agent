"""Database session management."""

import logging
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import settings
from src.core.model_normalization import (
    normalize_model_for_provider,
    normalize_provider_name,
)
from src.core.time_utils import utc_now_naive
from src.database.models import AgentConfiguration, AnalysisRun, Base

logger = logging.getLogger(__name__)

HARDENING_COLUMNS: tuple[tuple[str, str, str, str | None], ...] = (
    ("stories", "parsed_metadata", "TEXT", "'{}'"),
    ("sources", "bias_provenance", "VARCHAR(50)", "'unknown'"),
    ("sources", "is_curated_source", "BOOLEAN", "0"),
    ("sources", "bias_category", "VARCHAR(50)", None),
    ("sources", "relevance_score", "FLOAT", None),
    ("sources", "source_score", "FLOAT", None),
    ("sources", "bucket_label", "VARCHAR(50)", None),
    ("sources", "exact_bias", "INTEGER", None),
    ("sources", "coverage_type", "VARCHAR(50)", None),
    ("sources", "extractor_method", "VARCHAR(80)", None),
    ("sources", "extraction_error", "TEXT", None),
    ("sources", "extraction_error_code", "VARCHAR(80)", None),
    ("sources", "http_status", "INTEGER", None),
    ("sources", "og_image_url", "VARCHAR(2048)", None),
    ("sources", "embedded_post_urls_json", "TEXT", "'[]'"),
    ("sources", "image_alt_text_json", "TEXT", "'[]'"),
    ("sources", "media_captions_json", "TEXT", "'[]'"),
    ("sources", "relevance_diagnostics_json", "TEXT", "'{}'"),
    ("sources", "media_diagnostics_json", "TEXT", "'{}'"),
    ("sources", "key_framing", "TEXT", "''"),
    ("analyses", "structured_claims", "TEXT", "'{}'"),
    ("analyses", "coverage_asymmetry", "TEXT", "'{}'"),
    ("analyses", "narrative_json", "TEXT", "'{}'"),
    ("analyses", "coverage_snapshot_json", "TEXT", "'{}'"),
    ("analyses", "candidate_census_json", "TEXT", "'{}'"),
    ("analyses", "visual_evidence_json", "TEXT", "'{}'"),
    ("analyses", "report_validation_warnings_json", "TEXT", "'[]'"),
    ("analyses", "agent_handoff_snapshot_json", "TEXT", "'{}'"),
    ("analysis_runs", "options_snapshot_json", "TEXT", "'{}'"),
    ("analysis_runs", "report_validation_warnings_json", "TEXT", "'[]'"),
    ("channel_profiles", "owner_user_id", "VARCHAR(36)", None),
    ("channel_profiles", "raw_content", "TEXT", "''"),
    ("channel_profiles", "format", "VARCHAR(20)", "'yaml'"),
    ("channel_profiles", "parsed_json", "TEXT", "'{}'"),
    ("channel_profiles", "version", "INTEGER", "1"),
)


def get_database_url() -> str:
    """Get database URL, creating data directory if needed."""
    db_url = settings.database_url

    # If SQLite, ensure the directory exists
    if db_url.startswith("sqlite:///"):
        db_path = db_url.replace("sqlite:///", "")
        db_dir = Path(db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

    return db_url


# Create engine
engine = create_engine(
    get_database_url(),
    echo=settings.debug,
    connect_args={"check_same_thread": False}
    if "sqlite" in settings.database_url
    else {},
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Initialize missing database tables and safe seed/backfill rows.

    Existing schema changes are intentionally left to Alembic migrations. This
    keeps normal API/CLI startup from masking drift in already-created tables.
    """
    Base.metadata.create_all(bind=engine)
    if not _agent_config_schema_ready(engine):
        logger.warning(
            "Skipping agent configuration backfills because the database schema "
            "is not current. Run `research-agent init` to apply migrations."
        )
        return
    ensure_agent_config_rows(engine)
    backfill_agent_config_models(engine)
    backfill_known_bad_agent_models(engine)


def mark_interrupted_analysis_runs() -> int:
    """Fail analysis runs left open by a prior backend process."""
    with SessionLocal() as session:
        count = (
            session.query(AnalysisRun)
            .filter(AnalysisRun.status == "running")
            .update(
                {
                    "status": "failed",
                    "error": "interrupted_backend_restart",
                    "completed_at": utc_now_naive(),
                },
                synchronize_session=False,
            )
        )
        session.commit()

    if count:
        logger.warning(
            "Marked %d interrupted analysis run(s) as failed after backend startup.",
            count,
        )
    return int(count)


def run_alembic_upgrade(database_url: str | None = None) -> tuple[bool, str]:
    """Run Alembic migrations to the latest revision when configured."""
    project_root = Path(__file__).resolve().parents[2]
    alembic_ini = project_root / "alembic.ini"
    migrations_dir = project_root / "migrations"
    if not alembic_ini.exists() or not migrations_dir.exists():
        return False, "Alembic migration files are not present."

    try:
        from alembic import command
        from alembic.config import Config

        config = Config(str(alembic_ini))
        config.set_main_option("script_location", str(migrations_dir))
        config.set_main_option("sqlalchemy.url", database_url or get_database_url())
        command.upgrade(config, "head")
    except Exception as exc:
        logger.warning("Alembic upgrade failed", exc_info=True)
        return False, f"Alembic upgrade failed: {exc}"

    return True, "Alembic migrations upgraded to head."


def get_alembic_revision_status(database_url: str | None = None) -> tuple[str, str]:
    """Return Alembic revision readiness without applying migrations."""
    project_root = Path(__file__).resolve().parents[2]
    alembic_ini = project_root / "alembic.ini"
    migrations_dir = project_root / "migrations"
    if not alembic_ini.exists() or not migrations_dir.exists():
        return "warn", "Alembic migration files are not present."

    try:
        from alembic.config import Config
        from alembic.migration import MigrationContext
        from alembic.script import ScriptDirectory

        target_url = database_url or get_database_url()
        config = Config(str(alembic_ini))
        config.set_main_option("script_location", str(migrations_dir))
        config.set_main_option("sqlalchemy.url", target_url)
        script = ScriptDirectory.from_config(config)
        heads = set(script.get_heads())
        target_engine = engine if database_url is None else create_engine(target_url)
        try:
            with target_engine.connect() as connection:
                context = MigrationContext.configure(connection)
                current_heads = set(context.get_current_heads())
        finally:
            if database_url is not None:
                target_engine.dispose()
    except Exception as exc:
        logger.warning("Alembic revision check failed", exc_info=True)
        return "error", f"Could not inspect Alembic revision state: {exc}"

    if current_heads == heads:
        head_text = ", ".join(sorted(heads)) or "none"
        return "ok", f"Database is at Alembic head: {head_text}."
    if not current_heads:
        return "warn", "Database is not stamped with an Alembic revision."
    return (
        "warn",
        "Database revision "
        + ", ".join(sorted(current_heads))
        + " is not at head "
        + ", ".join(sorted(heads))
        + ".",
    )


def _default_fallback_model(provider: str) -> str:
    """Get fallback model for a provider using router defaults."""
    from src.core.llm_provider_docker import FALLBACK_MODELS, LLMProvider

    try:
        return FALLBACK_MODELS.get(LLMProvider(provider), "")
    except Exception:
        return ""


def _agent_config_schema_ready(target_engine) -> bool:
    """Return whether agent_configurations can be safely queried by the ORM."""
    try:
        inspector = inspect(target_engine)
        if AgentConfiguration.__tablename__ not in inspector.get_table_names():
            return False
        columns = {
            column["name"]
            for column in inspector.get_columns(AgentConfiguration.__tablename__)
        }
    except Exception:
        logger.warning("Could not inspect agent configuration schema", exc_info=True)
        return False

    required_columns = set(AgentConfiguration.__table__.columns.keys())
    return required_columns <= columns


def ensure_agent_config_rows(target_engine) -> None:
    """Ensure a config row exists for each known agent role.

    Missing rows are created idempotently and existing rows are preserved.
    """
    from src.agents.config import AGENT_ROLES

    session = Session(bind=target_engine)
    try:
        rows = session.query(AgentConfiguration).all()
        by_name = {row.agent_name: row for row in rows}

        template = by_name.get("fact_extractor") or by_name.get("report_writer")

        default_provider = (
            normalize_provider_name(getattr(template, "provider", None))
            or normalize_provider_name(settings.llm_provider)
            or "openrouter"
        )

        default_model_raw = getattr(template, "model", None) or _default_fallback_model(
            default_provider
        )
        default_model = normalize_model_for_provider(
            default_provider, default_model_raw
        )
        default_free_tier = bool(getattr(template, "free_tier", False))

        created = 0
        for agent_name in AGENT_ROLES:
            if agent_name in by_name:
                continue
            session.add(
                AgentConfiguration(
                    agent_name=agent_name,
                    provider=default_provider,
                    model=default_model,
                    free_tier=default_free_tier,
                )
            )
            created += 1

        if created:
            session.commit()
            logger.info("Created %s missing agent_configurations rows", created)
        else:
            session.rollback()
    except Exception:
        session.rollback()
        logger.warning("Failed to backfill missing agent configurations", exc_info=True)
    finally:
        session.close()


def ensure_agent_config_schema(target_engine) -> None:
    """Ensure agent_configurations has required columns."""
    try:
        inspector = inspect(target_engine)
        if "agent_configurations" not in inspector.get_table_names():
            return
        columns = {
            column["name"] for column in inspector.get_columns("agent_configurations")
        }
        if "free_tier" not in columns:
            with target_engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE agent_configurations "
                        "ADD COLUMN free_tier BOOLEAN DEFAULT 0"
                    )
                )
        if "reasoning_effort" not in columns:
            with target_engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE agent_configurations "
                        "ADD COLUMN reasoning_effort VARCHAR(20)"
                    )
                )
    except Exception:
        # Avoid failing startup on migration issues
        return


def ensure_hardening_schema(target_engine) -> None:
    """Ensure existing SQLite databases have hardening-era columns.

    SQLAlchemy ``create_all`` creates missing tables but does not alter tables
    that already exist, so older local/Docker SQLite files need a light,
    idempotent schema sync at startup.
    """
    try:
        inspector = inspect(target_engine)
        tables = set(inspector.get_table_names())
        for table, column, sql_type, default in HARDENING_COLUMNS:
            if table not in tables:
                continue
            columns = {col["name"] for col in inspector.get_columns(table)}
            if column in columns:
                continue

            default_clause = f" DEFAULT {default}" if default is not None else ""
            not_null_clause = " NOT NULL" if default is not None else ""
            with target_engine.begin() as conn:
                conn.execute(
                    text(
                        f"ALTER TABLE {table} ADD COLUMN {column} "
                        f"{sql_type}{not_null_clause}{default_clause}"
                    )
                )
            inspector.clear_cache()
    except Exception:
        logger.warning("Failed to sync hardening database schema", exc_info=True)


KNOWN_BAD_AGENT_MODELS: dict[str, str] = {
    "google/gemma-3n-e4b-it:free": "Rejects developer/system instructions through OpenRouter.",
    "meta-llama/llama-4-maverick:free": "Stale or unavailable OpenRouter free model.",
}


def _safe_model_for_provider(provider: str) -> str:
    """Get a known-safe fallback model for the given provider."""
    default = _default_fallback_model(provider)
    normalized = normalize_model_for_provider(provider, default)
    return normalized or default


def backfill_agent_config_models(target_engine) -> None:
    """Normalize provider/model identifiers in agent_configurations.

    Idempotent and safe to run at startup.
    """
    session = Session(bind=target_engine)
    try:
        configs = session.query(AgentConfiguration).all()
        changed = 0
        for config in configs:
            normalized_provider = normalize_provider_name(config.provider)
            provider_for_model = normalized_provider or config.provider
            normalized_model = normalize_model_for_provider(
                provider_for_model, config.model
            )

            if normalized_provider and normalized_provider != config.provider:
                config.provider = normalized_provider
                changed += 1
            if normalized_model and normalized_model != (config.model or ""):
                config.model = normalized_model
                changed += 1

        if changed:
            session.commit()
            logger.info(
                "Normalized %s agent configuration provider/model values", changed
            )
        else:
            session.rollback()
    except Exception:
        session.rollback()
    finally:
        session.close()


def backfill_known_bad_agent_models(target_engine) -> None:
    """Replace known-bad agent model IDs with safe fallbacks.

    Idempotent. Safe to run at startup.
    """
    session = Session(bind=target_engine)
    try:
        configs = session.query(AgentConfiguration).all()
        changed = 0
        for config in configs:
            model_key = (config.model or "").strip().lower()
            if model_key in KNOWN_BAD_AGENT_MODELS:
                old_model = config.model
                config.provider = (
                    normalize_provider_name(config.provider) or config.provider
                )
                config.model = _safe_model_for_provider(config.provider)
                logger.warning(
                    "Replaced known-bad agent model for %s: %s -> %s (%s)",
                    config.agent_name,
                    old_model,
                    config.model,
                    KNOWN_BAD_AGENT_MODELS[model_key],
                )
                changed += 1
        if changed:
            session.commit()
        else:
            session.rollback()
    except Exception:
        session.rollback()
        logger.warning("Failed to backfill known-bad agent models", exc_info=True)
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """Get database session as dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session() -> Session:
    """Get a new database session (manual lifecycle management)."""
    return SessionLocal()
