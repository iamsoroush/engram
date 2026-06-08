"""Add patient_memory AI job type + ai_jobs.patient_id (combined patient summary/history job).

Revision ID: 20260608140000
Revises: 20260608130000
Create Date: 2026-06-08 14:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260608140000"
down_revision = "20260608130000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres 12+ allows ADD VALUE inside a transaction as long as the value isn't used in the
    # same transaction (we only add it + a column here, so this is safe).
    op.execute("ALTER TYPE ai_job_type ADD VALUE IF NOT EXISTS 'patient_memory'")
    op.add_column("ai_jobs", sa.Column("patient_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_ai_jobs_patient_id_patients",
        "ai_jobs",
        "patients",
        ["patient_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_ai_jobs_tenant_id_patient_id", "ai_jobs", ["tenant_id", "patient_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_jobs_tenant_id_patient_id", table_name="ai_jobs")
    op.drop_constraint("fk_ai_jobs_patient_id_patients", "ai_jobs", type_="foreignkey")
    op.drop_column("ai_jobs", "patient_id")
    # Note: Postgres enum values cannot be dropped; 'patient_memory' is left in the type on downgrade.
