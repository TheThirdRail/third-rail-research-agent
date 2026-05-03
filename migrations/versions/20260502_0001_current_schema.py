"""Bootstrap current application schema.

Revision ID: 20260502_0001
Revises:
Create Date: 2026-05-02
"""

from collections.abc import Sequence

from alembic import op

from src.database.models import Base
from src.database.session import ensure_agent_config_schema, ensure_hardening_schema

revision: str = "20260502_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    ensure_hardening_schema(bind.engine)
    ensure_agent_config_schema(bind.engine)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
