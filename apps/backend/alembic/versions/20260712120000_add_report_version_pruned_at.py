"""Add session_report_versions.pruned_at (E17 redo semantics: forward-branch prune).

After a restore/undo, later report versions stay navigable-forward (redo re-effects the soft-deleted
captures). Adding a NEW capture while behind head branches away and abandons that forward line: those
versions leave the timeline UI (pruned_at set) but stay as DB rows (append-only store; debugging).
Nullable + default NULL, so every existing version stays visible. See
docs/architecture/pipeline-versioning.md.

Revision ID: 20260712120000
Revises: 20260706120000
Create Date: 2026-07-12 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260712120000"
down_revision: str | None = "20260706120000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "session_report_versions",
        sa.Column("pruned_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("session_report_versions", "pruned_at")
