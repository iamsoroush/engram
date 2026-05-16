"""add auth refresh tokens

Revision ID: 20260514152000
Revises: 20260514134037
Create Date: 2026-05-14 15:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260514152000"
down_revision: str | None = "20260514134037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_auth_refresh_tokens_tenant_id_tenants"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_auth_refresh_tokens_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_refresh_tokens")),
        sa.UniqueConstraint("jti", name="uq_auth_refresh_tokens_jti"),
    )
    op.create_index(
        "ix_auth_refresh_tokens_user_id_expires_at",
        "auth_refresh_tokens",
        ["user_id", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_auth_refresh_tokens_user_id_expires_at", table_name="auth_refresh_tokens")
    op.drop_table("auth_refresh_tokens")
