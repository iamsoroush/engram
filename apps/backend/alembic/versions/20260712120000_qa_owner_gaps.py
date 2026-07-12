"""Q&A owner-testing gaps: urgent escalation flag + retrieval-grounding backfill.

Two owner-found gaps (AES-1801 / AES-1802):

* **Escalation** — ``qa_messages.urgent`` (+ ``urgent_flags``): a patient question that trips the
  deterministic red-flag lexicon at ingest is marked urgent so the inbox / badge / bell escalate.
* **Grounding** — ``search_text`` now folds the exemplar **title** too (a topic-label title like
  «ورزش بعد از بوتاکس» must match «کی میتونم ورزش کنم؟»). This rebuilds every row's ``search_text``
  (+ ``language``) with the new formula, and repairs the owner's mis-entry trap: a template whose
  ``question`` is NULL but whose ``title`` reads as a question has the title moved into ``question``
  (the redesigned Library makes ``question`` the primary field, ``title`` an optional label — leaving
  a full question sitting in the label would be noise, so this is a move, not a copy).

Embeddings are NOT recomputed here (the migration must not call a gateway); the startup / maintenance
backfill (``app.maintenance.embed_backfill``) re-embeds NULL rows once a gateway is configured.

Revision ID: 20260712120000
Revises: 20260706120000
Create Date: 2026-07-12 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.services.qa_knowledge import normalize

revision: str = "20260712120000"
down_revision: str | None = "20260706120000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) Escalation flag (AES-1801).
    op.add_column("qa_messages", sa.Column("urgent", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("qa_messages", sa.Column("urgent_flags", JSONB, nullable=True))

    # 2) Grounding backfill (AES-1802): repair mis-entered titles, then rebuild search_text + language
    #    with the new title-inclusive formula so existing rows match on their topic-label title.
    bind = op.get_bind()
    exemplars = sa.table(
        "qa_knowledge_exemplars",
        sa.column("id", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.column("kind", sa.String),
        sa.column("title", sa.Text),
        sa.column("question", sa.Text),
        sa.column("answer", sa.Text),
        sa.column("search_text", sa.Text),
        sa.column("language", sa.String),
    )
    rows = bind.execute(
        sa.select(exemplars.c.id, exemplars.c.kind, exemplars.c.title, exemplars.c.question, exemplars.c.answer)
    ).all()
    for row in rows:
        title, question = row.title, row.question
        # Move a question-shaped title into the empty question field (the owner's mis-entry trap).
        if row.kind == "template" and not (question or "").strip() and normalize.looks_like_question(title):
            question, title = title, None
        search_text = normalize.build_search_text(title=title, question=question, answer=row.answer)
        language = normalize.detect_language(f"{title or ''} {question or ''} {row.answer or ''}")
        bind.execute(
            exemplars.update()
            .where(exemplars.c.id == row.id)
            .values(title=title, question=question, search_text=search_text, language=language)
        )


def downgrade() -> None:
    op.drop_column("qa_messages", "urgent_flags")
    op.drop_column("qa_messages", "urgent")
    # search_text/question backfill is a data repair, not reversible structure — intentionally not undone.
