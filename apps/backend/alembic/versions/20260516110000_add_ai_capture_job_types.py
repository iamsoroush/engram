"""add ai capture job types

Revision ID: 20260516110000
Revises: 20260514165000
Create Date: 2026-05-16 11:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260516110000"
down_revision: str | None = "20260514165000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE ai_job_type ADD VALUE IF NOT EXISTS 'audio_capture_process'")
    op.execute("ALTER TYPE ai_job_type ADD VALUE IF NOT EXISTS 'text_capture_process'")
    op.execute("ALTER TYPE ai_job_type ADD VALUE IF NOT EXISTS 'image_capture_process'")


def downgrade() -> None:
    # PostgreSQL cannot remove enum values without recreating the type.
    pass
