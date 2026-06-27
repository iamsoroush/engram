"""Add ai_feedback_events (AI-quality harvester; eval golden-set, eval-epic §1b).

Records every staff correction of an AI output (transcript/caption/treatment/patient-match) and every
report/brief thumbs rating as a candidate eval case. Append-only; correction rows are written in the
same transaction as the edit they record (like audit_events). Structured patient PII never enters the
``context`` column (scrubbed in ``services.feedback``); the before/after AI-output text is the eval
target and is stored verbatim.

Revision ID: 20260625120000
Revises: 20260622120000
Create Date: 2026-06-25 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "20260625120000"
down_revision: str | None = "20260622120000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_feedback_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("ai_output_type", sa.String(length=40), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), nullable=True),
        sa.Column("capture_id", UUID(as_uuid=True), nullable=True),
        sa.Column("patient_id", UUID(as_uuid=True), nullable=True),
        sa.Column("before_value", sa.Text(), nullable=True),
        sa.Column("after_value", sa.Text(), nullable=True),
        sa.Column("rating", sa.SmallInteger(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("context", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["capture_id"], ["captures.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_ai_feedback_events_tenant_id_created_at",
        "ai_feedback_events",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_ai_feedback_events_tenant_id_kind_output",
        "ai_feedback_events",
        ["tenant_id", "kind", "ai_output_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_feedback_events_tenant_id_kind_output", table_name="ai_feedback_events")
    op.drop_index("ix_ai_feedback_events_tenant_id_created_at", table_name="ai_feedback_events")
    op.drop_table("ai_feedback_events")
