"""Add ai_usage_counters (fair-use AI metering: real spend + volume per clinic/seat/period).

Source of truth for the AI usage-limit system. One row per (tenant, user, period_key = "YYYY-MM").
Written when a gateway-billed AI job completes (real gateway ``usage`` → cost via the pricing table).
The clinic total for a period is the SUM over its seats. cost stored in micro-dollars (int).

Revision ID: 20260702120000
Revises: 20260628120000
Create Date: 2026-07-02 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260702120000"
down_revision: str | None = "20260628120000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_counters",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("period_key", sa.String(length=7), nullable=False),
        sa.Column("cost_micros", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("ai_captures", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("audio_seconds", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("synthesis_runs", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("ai_jobs", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    # NULLS NOT DISTINCT (PG >= 15) so clinic-scoped rows with a NULL user_id collapse to one row and
    # increment atomically via ON CONFLICT (default NULL-distinct semantics would duplicate them).
    op.create_index(
        "uq_ai_usage_tenant_user_period",
        "ai_usage_counters",
        ["tenant_id", "user_id", "period_key"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )
    op.create_index("ix_ai_usage_counters_tenant_period", "ai_usage_counters", ["tenant_id", "period_key"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_counters_tenant_period", table_name="ai_usage_counters")
    op.drop_table("ai_usage_counters")
