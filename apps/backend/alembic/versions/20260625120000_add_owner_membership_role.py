"""Add the owner membership role (clinic founder created by self-serve sign-up).

``owner`` is a full superset of the staff + admin roles: the founding user can both capture and
administer their tenant, and is always ``full`` in the multi-seat permission model. Additive — it
never alters the existing doctor/assistant/admin/patient semantics, so only the enum value is added.

Revision ID: 20260625120000
Revises: 20260622120000
Create Date: 2026-06-25 12:00:00.000000
"""
from collections.abc import Sequence

from alembic import op

revision: str = "20260625120000"
down_revision: str | None = "20260622120000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE membership_role ADD VALUE IF NOT EXISTS 'owner'")


def downgrade() -> None:
    # PostgreSQL cannot remove an enum value without recreating the type; left in place.
    pass
