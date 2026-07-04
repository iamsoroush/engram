"""Add the Q&A knowledge library (pgvector exemplar store) + draft provenance.

The retrieval corpus behind grounded qa_draft (AES-410): a per-tenant table of curated templates +
auto-indexed doctor-approved sent replies, each with a normalized lexical `search_text` and an
OPTIONAL native pgvector `embedding` (populated only when the embeddings gateway is configured;
NULL rows still rank lexically). Also adds `qa_messages.draft_provenance` — the top exemplar a draft
was grounded in, surfaced as the doctor-only "based on: {template}" chip.

Decision-complete: pgvector inside the existing Postgres (no new infra) — the Postgres image is
`pgvector/pgvector:pg16`. `CREATE EXTENSION IF NOT EXISTS vector` is idempotent and per-database, so
it is safe on the canonical DB, every dev-stack clone, e2e, and prod. See
docs/technical-decisions.md ("Q&A Knowledge Retrieval — pgvector in the existing Postgres").

Revision ID: 20260705120000
Revises: 20260702120000
Create Date: 2026-07-05 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "20260705120000"
down_revision: str | None = "20260702120000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgvector: idempotent, per-database. Requires a Postgres image that ships the extension
    # (pgvector/pgvector:pg16) — see the module docstring / technical-decisions.md.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "qa_knowledge_exemplars",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=8), server_default="und", nullable=False),
        sa.Column("tags", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("search_text", sa.Text(), server_default="", nullable=False),
        sa.Column("source_message_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_message_id"], ["qa_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    # Native, dimensionless pgvector column (raw DDL — SQLAlchemy core has no vector type).
    op.execute("ALTER TABLE qa_knowledge_exemplars ADD COLUMN embedding vector")

    op.create_index(
        "ix_qa_knowledge_tenant_status_kind",
        "qa_knowledge_exemplars",
        ["tenant_id", "status", "kind"],
    )
    # One indexed exemplar per sent reply (auto-index idempotency); partial so templates (NULL source)
    # are unconstrained.
    op.create_index(
        "uq_qa_knowledge_source_message",
        "qa_knowledge_exemplars",
        ["tenant_id", "source_message_id"],
        unique=True,
        postgresql_where=sa.text("source_message_id IS NOT NULL"),
    )

    op.add_column("qa_messages", sa.Column("draft_provenance", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("qa_messages", "draft_provenance")
    op.drop_index("uq_qa_knowledge_source_message", table_name="qa_knowledge_exemplars")
    op.drop_index("ix_qa_knowledge_tenant_status_kind", table_name="qa_knowledge_exemplars")
    op.drop_table("qa_knowledge_exemplars")
    # Intentionally do NOT drop the `vector` extension on downgrade — other objects may use it and
    # dropping an extension is not reversible state we own.
