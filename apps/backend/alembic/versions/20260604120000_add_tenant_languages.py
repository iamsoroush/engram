"""Add tenant transcription/report language preferences.

Revision ID: 20260604120000
Revises: 20260603120000
Create Date: 2026-06-04 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260604120000"
down_revision = "20260603120000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Transcription default "auto" = transcribe verbatim in the spoken language/script.
    op.add_column("tenants", sa.Column("transcription_language", sa.String(length=20), server_default="auto", nullable=False))
    # Report language NULL = follow the report template's default language.
    op.add_column("tenants", sa.Column("report_language", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "report_language")
    op.drop_column("tenants", "transcription_language")
