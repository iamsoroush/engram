"""Add aftercare_templates (aesthetics-Basic, AES-702).

Per-procedure deterministic aftercare instruction templates managed in Settings and attached to a
curated patient share (AES-304). Plain table, no enum DDL.

Revision ID: 20260612120000
Revises: 20260611120000
Create Date: 2026-06-12 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260612120000"
down_revision = "20260611120000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "aftercare_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("procedure_type", sa.String(length=120), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_aftercare_templates_tenant_id_procedure_type",
        "aftercare_templates",
        ["tenant_id", "procedure_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_aftercare_templates_tenant_id_procedure_type", table_name="aftercare_templates")
    op.drop_table("aftercare_templates")
