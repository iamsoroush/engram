"""Add durable AI job retry schedule.

Revision ID: 20260602120000
Revises: 20260521120000
Create Date: 2026-06-02 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260602120000"
down_revision = "20260521120000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_jobs", sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column("ai_jobs", sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ai_jobs", sa.Column("last_dispatched_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ai_jobs", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ai_jobs", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column("ai_jobs", sa.Column("retry_reason", sa.String(length=120), nullable=True))
    op.create_index("ix_ai_jobs_status_next_retry_at", "ai_jobs", ["status", "next_retry_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_jobs_status_next_retry_at", table_name="ai_jobs")
    op.drop_column("ai_jobs", "retry_reason")
    op.drop_column("ai_jobs", "last_error")
    op.drop_column("ai_jobs", "next_retry_at")
    op.drop_column("ai_jobs", "last_dispatched_at")
    op.drop_column("ai_jobs", "last_attempted_at")
    op.drop_column("ai_jobs", "attempt_count")
