"""Add post-session patient Q&A (Pro payload of the patient surface; AES-402).

Adds two tables — ``qa_threads`` (one tokenized, revocable Q&A channel per patient) and
``qa_messages`` (patient questions + doctor-verified replies, with the AI-suggested draft on each
question) — plus the tenant ``qa_routing_mode`` policy column, and the ``qa_draft`` value on the
existing ``ai_job_type`` enum (the Q&A reply-draft job reuses the patient-scoped AiJob with the
target message carried in ``result_metadata`` — no ai_jobs schema change).

Revision ID: 20260613120000
Revises: 20260612130000
Create Date: 2026-06-13 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260613120000"
down_revision = "20260612130000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tenant-level routing policy (admin-configurable; default = AI routes to the treating doctor).
    op.add_column(
        "tenants",
        sa.Column("qa_routing_mode", sa.String(length=20), server_default="ai_default", nullable=False),
    )

    # New patient-scoped AI job type for the doctor-verified reply draft.
    op.execute("ALTER TYPE ai_job_type ADD VALUE IF NOT EXISTS 'qa_draft'")

    op.create_table(
        "qa_threads",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", UUID(as_uuid=True), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("assigned_doctor_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("routing_source", sa.String(length=20), server_default="ai_default", nullable=False),
        sa.Column("created_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_doctor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("token", name="uq_qa_threads_token"),
        sa.UniqueConstraint("tenant_id", "patient_id", name="uq_qa_threads_tenant_id_patient_id"),
    )
    op.create_index(
        "ix_qa_threads_tenant_id_assigned_doctor",
        "qa_threads",
        ["tenant_id", "assigned_doctor_user_id"],
    )

    op.create_table(
        "qa_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("in_reply_to_id", UUID(as_uuid=True), nullable=True),
        sa.Column("draft", sa.Text(), nullable=True),
        sa.Column("draft_status", sa.String(length=20), server_default="none", nullable=False),
        sa.Column("draft_source", sa.String(length=80), nullable=True),
        sa.Column("draft_job_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["qa_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["in_reply_to_id"], ["qa_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_qa_messages_tenant_id_thread_id", "qa_messages", ["tenant_id", "thread_id"])
    op.create_index("ix_qa_messages_tenant_id_role_status", "qa_messages", ["tenant_id", "role", "status"])


def downgrade() -> None:
    op.drop_index("ix_qa_messages_tenant_id_role_status", table_name="qa_messages")
    op.drop_index("ix_qa_messages_tenant_id_thread_id", table_name="qa_messages")
    op.drop_table("qa_messages")
    op.drop_index("ix_qa_threads_tenant_id_assigned_doctor", table_name="qa_threads")
    op.drop_table("qa_threads")
    op.drop_column("tenants", "qa_routing_mode")
    # PostgreSQL cannot remove an enum value without recreating the type; 'qa_draft' is left in place.
