"""Add tenant intelligence tier.

Revision ID: 20260603120000
Revises: 20260602120000
Create Date: 2026-06-03 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260603120000"
down_revision = "20260602120000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("tier", sa.String(length=20), server_default="pro", nullable=False))


def downgrade() -> None:
    op.drop_column("tenants", "tier")
