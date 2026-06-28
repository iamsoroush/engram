"""Add session_report_versions (pipeline-versioning: content-addressed report_version store).

An immutable, content-addressed snapshot of a session's synthesized report + structured artifacts,
keyed by capture_set_hash (hash of the ordered in-context capture-versions) so an undo that returns the
session to a previously-seen capture set is a deterministic cache-hit restore (no LLM). The user-state
overlay is NOT stored here. See docs/architecture/pipeline-versioning.md.

Revision ID: 20260628120000
Revises: 20260627120000
Create Date: 2026-06-28 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "20260628120000"
down_revision: str | None = "20260627120000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "session_report_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("capture_set_hash", sa.String(length=64), nullable=False),
        sa.Column("captured_capture_version_ids", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("artifacts", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("generated_by", sa.String(length=40), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pinned", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_session_report_versions_session_created",
        "session_report_versions",
        ["tenant_id", "session_id", "created_at"],
    )
    op.create_index(
        "ix_session_report_versions_session_hash",
        "session_report_versions",
        ["tenant_id", "session_id", "capture_set_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_session_report_versions_session_hash", table_name="session_report_versions")
    op.drop_index("ix_session_report_versions_session_created", table_name="session_report_versions")
    op.drop_table("session_report_versions")
