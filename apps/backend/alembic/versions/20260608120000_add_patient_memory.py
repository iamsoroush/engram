"""Add patient memory blob (mock tier-aware summary/history lifecycle).

Revision ID: 20260608120000
Revises: 20260605130000
Create Date: 2026-06-08 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260608120000"
down_revision = "20260605130000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable, no server default: NULL = no memory generated yet (read falls back to rule-based).
    op.add_column("patients", sa.Column("memory", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("patients", "memory")
