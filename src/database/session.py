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
from src.database.models import AgentConfiguration, Base

logger = logging.getLogger(__name__)

HARDENING_COLUMNS: tuple[tuple[str, str, str, str | None], ...] = (
    ("stories", "parsed_metadata", "TEXT", "'{}'"),
    ("sources", "bias_provenance", "VARCHAR(50)", "'unknown'"),
    ("sources", "is_curated_source", "BOOLEAN", "0"),
    ("sources", "bias_category", "VARCHAR(50)", None),
    ("analyses", "structured_claims", "TEXT", "'{}'"),
    ("analyses", "coverage_asymmetry", "TEXT", "'{}'"),
    ("analyses", "narrative_json", "TEXT", "'{}'"),
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
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)
    ensure_hardening_schema(engine)
    ensure_agent_config_schema(engine)
    ensure_agent_config_rows(engine)
    backfill_agent_config_models(engine)


def _default_fallback_model(provider: str) -> str:
    """Get fallback model for a provider using router defaults."""
    from src.core.llm_provider_docker import FALLBACK_MODELS, LLMProvider

    try:
        return FALLBACK_MODELS.get(LLMProvider(provider), "")
    except Exception:
        return ""


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
