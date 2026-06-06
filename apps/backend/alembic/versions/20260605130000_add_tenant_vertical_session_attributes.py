"""Add tenant vertical + session attributes extension point (A0).

Revision ID: 20260605130000
Revises: 20260605120000
Create Date: 2026-06-05 13:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "20260605130000"
down_revision = "20260605120000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Vertical: "clinic" (v1) | "radiology" | "pathology" | … — types the generic Encounter
    # (today's Session) and drives its presentation label.
    op.add_column("tenants", sa.Column("vertical", sa.String(length=40), server_default="clinic", nullable=False))
    # Per-vertical typed fields for the Encounter (reserved; empty for clinics).
    op.add_column("sessions", sa.Column("attributes", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False))


def downgrade() -> None:
    op.drop_column("sessions", "attributes")
    op.drop_column("tenants", "vertical")
