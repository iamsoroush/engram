"""Add the qa_revise AI job type (Q&A voice edit; AES-402).

The doctor's spoken note revises/replaces a Q&A reply draft. Reuses the patient-scoped AiJob (the
target message + audio object key live in result_metadata), so only the enum value is added.

Revision ID: 20260615120000
Revises: 20260613130000
Create Date: 2026-06-15 12:00:00.000000
"""
from collections.abc import Sequence

from alembic import op

revision: str = "20260615120000"
down_revision: str | None = "20260613130000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE ai_job_type ADD VALUE IF NOT EXISTS 'qa_revise'")


def downgrade() -> None:
    # PostgreSQL cannot remove an enum value without recreating the type; left in place.
    pass
