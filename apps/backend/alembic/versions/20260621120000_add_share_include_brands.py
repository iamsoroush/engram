"""Add tenants.share_include_brands (Story C, decision 2).

Per-clinic control for whether a curated patient share's plain-words "what we did" treatment line may
include commercial brand names. Default OFF (generic category only); dose tables + lots stay
always-withheld server-side regardless.

Revision ID: 20260621120000
Revises: 20260615120000
Create Date: 2026-06-21 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260621120000"
down_revision: str | None = "20260615120000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("share_include_brands", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("tenants", "share_include_brands")
