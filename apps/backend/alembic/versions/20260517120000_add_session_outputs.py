"""add session draft status and generated outputs

Revision ID: 20260517120000
Revises: 20260516110000
Create Date: 2026-05-17 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260517120000"
down_revision: str | None = "20260516110000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE session_status ADD VALUE IF NOT EXISTS 'draft' BEFORE 'unassigned'")
    op.add_column("sessions", sa.Column("generated_report", sa.Text(), nullable=True))
    op.add_column(
        "sessions",
        sa.Column(
            "extracted_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("sessions", sa.Column("report_template_key", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "report_template_key")
    op.drop_column("sessions", "extracted_metadata")
    op.drop_column("sessions", "generated_report")
    # PostgreSQL cannot remove enum values without recreating the type.
