"""Add patient_shares (patient surface; AES-303/304/401/403).

A tokenized, revocable clinic→patient share of a CURATED content snapshot (selected sections +
media refs + aftercare). ``status`` is a plain String ("active"/"revoked") to match
tier/match_strictness/vertical — no enum DDL.

Revision ID: 20260612130000
Revises: 20260612120000
Create Date: 2026-06-12 13:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260612130000"
down_revision = "20260612120000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "patient_shares",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), nullable=True),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("payload_type", sa.String(length=40), server_default="report_aftercare", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("content", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("token", name="uq_patient_shares_token"),
    )
    op.create_index(
        "ix_patient_shares_tenant_id_patient_id",
        "patient_shares",
        ["tenant_id", "patient_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_patient_shares_tenant_id_patient_id", table_name="patient_shares")
    op.drop_table("patient_shares")
