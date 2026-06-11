"""Expand tenant vertical taxonomy to Spine-A verticals (P0.2).

Drop the legacy "clinic" vertical: data-migrate existing tenants to "aesthetics" (the current
product, now the default) and change the column server_default from "clinic" to "aesthetics".
Plain String column — no enum DDL.

Revision ID: 20260611120000
Revises: 20260608140000
Create Date: 2026-06-11 12:00:00.000000
"""

from alembic import op


revision = "20260611120000"
down_revision = "20260608140000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE tenants SET vertical = 'aesthetics' WHERE vertical = 'clinic'")
    op.alter_column("tenants", "vertical", server_default="aesthetics")


def downgrade() -> None:
    op.alter_column("tenants", "vertical", server_default="clinic")
    op.execute("UPDATE tenants SET vertical = 'clinic' WHERE vertical = 'aesthetics'")
