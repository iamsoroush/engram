"""Add global app_config key/value table (live AI model selection).

Revision ID: 20260608130000
Revises: 20260608120000
Create Date: 2026-06-08 13:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260608130000"
down_revision = "20260608120000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_config",
        sa.Column("key", sa.String(length=120), primary_key=True),
        sa.Column("value", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("updated_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )


def downgrade() -> None:
    op.drop_table("app_config")
