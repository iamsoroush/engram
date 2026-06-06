"""Add tenant match-strictness preference (H3).

Revision ID: 20260605120000
Revises: 20260604120000
Create Date: 2026-06-05 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260605120000"
down_revision = "20260604120000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # "strict" = auto-apply deterministic matches only (preserves prior behavior).
    # "balanced"/"lenient" auto-apply a single high-confidence fuzzy match on an explicit
    # reassignment instruction; the national-ID conflict guard wins at every level.
    op.add_column(
        "tenants",
        sa.Column("match_strictness", sa.String(length=20), server_default="strict", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("tenants", "match_strictness")
