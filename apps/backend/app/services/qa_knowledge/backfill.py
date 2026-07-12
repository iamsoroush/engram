"""(Re)embed Q&A knowledge exemplars whose ``embedding`` is NULL (AES-1802).

Embeddings are OPTIONAL: a row indexed while the gateway was unconfigured (dev/CI, or before the
gateway was wired) stores ``search_text`` but a NULL vector, so it ranks lexical-only. When a gateway
later becomes available this backfill fills those gaps so semantic matching turns on for the whole
corpus, not just newly-written rows. Idempotent, bounded, best-effort: a gateway hiccup leaves the
row NULL (still lexically retrievable) and the next run retries it.

Callable at startup (guarded on ``embeddings_configured``) and from the maintenance CLI
(``python -m app.maintenance.embed_backfill``).
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import QaKnowledgeExemplar
from app.services.qa_knowledge.embeddings import embed_text, embeddings_configured

logger = logging.getLogger(__name__)

# Bound one pass so a large corpus (or a flaky gateway) can't stall startup; the next run continues.
DEFAULT_BACKFILL_LIMIT = 500


def backfill_missing_embeddings(db: DbSession, *, limit: int = DEFAULT_BACKFILL_LIMIT) -> int:
    """Embed up to ``limit`` exemplars with a NULL embedding. Returns how many were embedded.

    No-op (returns 0) when no gateway is configured — lexical-only stays the deterministic default for
    dev / CI / e2e. Commits once at the end; a per-row gateway failure is skipped (stays NULL).
    """
    if not embeddings_configured():
        return 0
    rows = list(
        db.execute(
            select(QaKnowledgeExemplar)
            .where(QaKnowledgeExemplar.embedding.is_(None))
            .order_by(QaKnowledgeExemplar.created_at.desc())
            .limit(limit)
        ).scalars()
    )
    embedded = 0
    for row in rows:
        vector = embed_text(row.search_text)
        if vector is None:
            continue  # gateway hiccup — leave NULL (still lexical); a later run retries.
        row.embedding = vector
        embedded += 1
    if embedded:
        db.commit()
    logger.info("Q&A embeddings backfill: embedded %d of %d NULL-embedding exemplars", embedded, len(rows))
    return embedded
