"""Add tenants.high_risk_clinic (session-layout-diet, AES-1304).

A clinic self-declares "high-risk"; when set, the session safety panel stays pinned open (never
collapses to a chip in the patient strip). Default OFF. Generalizes to other safety-forward
behaviors later from one honest setting.

Revision ID: 20260706120000
Revises: 20260705120000
Create Date: 2026-07-06 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260706120000"
down_revision: str | None = "20260705120000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("high_risk_clinic", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("tenants", "high_risk_clinic")
