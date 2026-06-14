"""Add multi-seat: tenant role_permissions + worklist_entries (E9, AES-903/905).

``tenants.role_permissions`` is a JSONB blob of per non-owner role presets
("contribute" | "reassign" | "full"); empty falls back to the permissive defaults in
``services.permissions``. ``worklist_entries`` is the soft "line a patient up for a clinician"
list (AES-903). ``status`` is a plain String to match tier/vertical/share-status — no enum DDL.

Revision ID: 20260613120000
Revises: 20260612130000
Create Date: 2026-06-13 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260613120000"
down_revision = "20260612130000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("role_permissions", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.create_table(
        "worklist_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", UUID(as_uuid=True), nullable=False),
        sa.Column("clinician_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="waiting", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("session_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clinician_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_worklist_entries_tenant_clinician_status",
        "worklist_entries",
        ["tenant_id", "clinician_user_id", "status"],
    )
    op.create_index(
        "ix_worklist_entries_tenant_status",
        "worklist_entries",
        ["tenant_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_worklist_entries_tenant_status", table_name="worklist_entries")
    op.drop_index("ix_worklist_entries_tenant_clinician_status", table_name="worklist_entries")
    op.drop_table("worklist_entries")
    op.drop_column("tenants", "role_permissions")
