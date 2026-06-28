"""Add patients.safety_flags (cross-visit clinical safety flags).

Session synthesis detects allergy/contraindication/consent statements (``safetyFlags``); the
non-rejected ones are persisted on the patient so they surface at future visits' point of care.
Kept in a dedicated JSONB column (not inside ``patients.memory``) so a Job-4 patient-memory rebuild
never wipes them. Deterministic, opt-out (the clinician rejects a wrong one). List of
{key, kind, text, sourceSessionId, sourceCaptureIds, addedAt}; see services/patient_safety.py.

Revision ID: 20260627120000
Revises: 20260625130000
Create Date: 2026-06-27 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260627120000"
down_revision: str | None = "20260625130000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "patients",
        sa.Column("safety_flags", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("patients", "safety_flags")
