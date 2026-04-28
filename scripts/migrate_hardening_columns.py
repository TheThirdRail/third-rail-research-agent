"""Migration script for hardening columns.

Adds new columns introduced by the pipeline hardening work.
Safe to run multiple times — each ALTER TABLE is wrapped in a
try/except that silently handles 'duplicate column' errors.

Usage:
    python -m scripts.migrate_hardening_columns
"""

import logging
import sqlite3
import sys

from src.core.config import settings

logger = logging.getLogger(__name__)


# (table, column, sql_type, default_value)
NEW_COLUMNS: list[tuple[str, str, str, str]] = [
    # Story
    ("stories", "parsed_metadata", "TEXT", "'{}'"),
    # Source
    ("sources", "bias_provenance", "VARCHAR(50)", "'unknown'"),
    ("sources", "is_curated_source", "BOOLEAN", "0"),
    ("sources", "bias_category", "VARCHAR(50)", "NULL"),
    # Analysis
    ("analyses", "structured_claims", "TEXT", "'{}'"),
    ("analyses", "coverage_asymmetry", "TEXT", "'{}'"),
    ("analyses", "narrative_json", "TEXT", "'{}'"),
    # ChannelProfile
    ("channel_profiles", "owner_user_id", "VARCHAR(36)", "NULL"),
    ("channel_profiles", "raw_content", "TEXT", "''"),
    ("channel_profiles", "format", "VARCHAR(20)", "'yaml'"),
    ("channel_profiles", "parsed_json", "TEXT", "'{}'"),
    ("channel_profiles", "version", "INTEGER", "1"),
]


def migrate(db_path: str | None = None) -> None:
    """Add new columns to an existing SQLite database.

    Args:
        db_path: Path to the SQLite database. If None, uses the
            configured database URL from settings.
    """
    if db_path is None:
        url = str(settings.database_url)
        if url.startswith("sqlite:///"):
            db_path = url.replace("sqlite:///", "")
        else:
            logger.error("Non-SQLite database; run Alembic instead.")
            return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    added = 0

    for table, column, sql_type, default in NEW_COLUMNS:
        try:
            default_clause = f" DEFAULT {default}" if default != "NULL" else ""
            null_clause = "" if default == "NULL" else " NOT NULL"
            stmt = (
                f"ALTER TABLE {table} ADD COLUMN {column} "
                f"{sql_type}{null_clause}{default_clause}"
            )
            cursor.execute(stmt)
            added += 1
            logger.info("Added %s.%s", table, column)
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                logger.debug("Column %s.%s already exists, skipping.", table, column)
            else:
                logger.warning("Failed to add %s.%s: %s", table, column, e)

    conn.commit()
    conn.close()
    logger.info("Migration complete: %d columns added.", added)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    path = sys.argv[1] if len(sys.argv) > 1 else None
    migrate(path)
