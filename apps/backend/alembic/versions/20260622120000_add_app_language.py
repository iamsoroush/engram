"""Add tenants.app_language (UI language + date calendar, distinct from report language).

app_language drives the clinic app's interface language and date formatting (Jalali when Persian).
report_language stays scoped to generated report/share CONTENT. Default "en".

Revision ID: 20260622120000
Revises: 20260621120000
Create Date: 2026-06-22 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260622120000"
down_revision: str | None = "20260621120000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("app_language", sa.String(length=20), nullable=False, server_default="en"))


def downgrade() -> None:
    op.drop_column("tenants", "app_language")
