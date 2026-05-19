"""add AI job succeeded status

Revision ID: 20260514165000
Revises: 20260514152000
Create Date: 2026-05-14 16:50:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260514165000"
down_revision: str | None = "20260514152000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE ai_job_status ADD VALUE IF NOT EXISTS 'succeeded'")


def downgrade() -> None:
    # PostgreSQL cannot remove enum values without recreating the type.
    pass
