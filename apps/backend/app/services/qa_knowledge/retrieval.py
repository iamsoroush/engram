"""Hybrid lexical + embedding retrieval over a tenant's Q&A knowledge exemplars.

The corpus is tiny (hundreds–low-thousands of short texts per clinic), so v1 is exact, not ANN: SQL
enforces **per-tenant scoping** (the hard multi-tenancy boundary) and fetches a capped active-candidate
set; ranking is then done in Python by fusing two signals — a lexical term-cosine over the folded
``search_text`` and an embedding cosine (only when an embeddings gateway is configured). Gateway-less,
retrieval is purely lexical and fully deterministic (dev / CI / e2e).

The ranking helpers (``lexical_score`` / ``cosine`` / ``fuse``) are pure and unit-tested; ``retrieve``
is the DB entry point that composes them.
"""
from __future__ import annotations

import math
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import settings
from app.models import QaKnowledgeExemplar
from app.services.qa_knowledge import normalize
from app.services.qa_knowledge.embeddings import embed_text

# When an embedding signal is available, split weight evenly with lexical; a same-language match gets a
# small nudge. An exemplar with neither lexical overlap nor a decent embedding match is not returned —
# a weak, off-topic "based on" would erode doctor trust more than an empty result.
_LEXICAL_WEIGHT = 0.5
_EMBEDDING_WEIGHT = 0.5
_EMBEDDING_FLOOR = 0.15
_SAME_LANGUAGE_BONUS = 0.05


def lexical_score(query_tokens: set[str], doc_tokens: set[str]) -> float:
    """Term-set cosine in [0,1]: |q∩d| / sqrt(|q|·|d|). 0 when either side is empty."""
    if not query_tokens or not doc_tokens:
        return 0.0
    overlap = len(query_tokens & doc_tokens)
    if overlap == 0:
        return 0.0
    return overlap / math.sqrt(len(query_tokens) * len(doc_tokens))


def cosine(a: list[float] | None, b: list[float] | None) -> float:
    """Cosine similarity in [-1,1]; 0.0 for a missing/empty/degenerate vector or a length mismatch."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def fuse(*, lex: float, emb: float | None, same_language: bool) -> float:
    """Blend the lexical + embedding signals into one score (embedding optional)."""
    if emb is None:
        score = lex
    else:
        score = _LEXICAL_WEIGHT * lex + _EMBEDDING_WEIGHT * max(0.0, emb)
    if same_language:
        score += _SAME_LANGUAGE_BONUS
    return score


def _eligible(lex: float, emb: float | None) -> bool:
    """Keep only candidates with real signal (some lexical overlap, or a decent embedding match)."""
    return lex > 0.0 or (emb is not None and emb >= _EMBEDDING_FLOOR)


def rank_candidates(
    candidates: list[dict[str, Any]],
    *,
    query: str,
    query_language: str,
    query_embedding: list[float] | None,
    top_k: int,
) -> list[dict[str, Any]]:
    """Pure ranking over already-fetched candidates → top-k exemplar dicts with a ``score``.

    Each candidate is ``{id, kind, title, question, answer, language, search_text, embedding}``; the
    returned dicts add ``score`` and drop the raw embedding. Deterministic: ties break by score then by
    the candidate's stable id, so the same corpus + query always yields the same order.
    """
    query_tokens = normalize.token_set(query)
    scored: list[tuple[float, str, dict[str, Any]]] = []
    for candidate in candidates:
        doc_tokens = normalize.token_set(candidate.get("search_text") or "")
        lex = lexical_score(query_tokens, doc_tokens)
        # Only blend an embedding signal when BOTH sides have a vector; a row indexed while the
        # embeddings gateway was down is scored on lexical alone (not penalized to half).
        emb = (
            cosine(query_embedding, candidate.get("embedding"))
            if query_embedding and candidate.get("embedding")
            else None
        )
        if not _eligible(lex, emb):
            continue
        same_language = (
            query_language in {"fa", "en"}
            and candidate.get("language") == query_language
        )
        score = fuse(lex=lex, emb=emb, same_language=same_language)
        scored.append(
            (
                score,
                str(candidate.get("id")),
                {
                    "exemplarId": str(candidate.get("id")),
                    "kind": candidate.get("kind"),
                    "title": candidate.get("title"),
                    "question": candidate.get("question"),
                    "answer": candidate.get("answer"),
                    "language": candidate.get("language"),
                    "score": round(score, 4),
                },
            )
        )
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [entry for _, _, entry in scored[: max(0, top_k)]]


def retrieve(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    query: str,
    language: str | None = None,
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """Retrieve the top exemplars for a question — SQL-scoped to the tenant, ranked in Python.

    Returns ``[]`` when the query is empty or nothing is eligible. Embeds the query only when a gateway
    is configured (else lexical-only). The candidate set is capped (`qa_retrieval_candidate_cap`) and
    fetched newest-first so a giant corpus can't blow up memory; for the intended tiny corpora the cap
    is never hit.
    """
    text = (query or "").strip()
    if not text:
        return []
    limit = top_k if top_k is not None else settings.qa_retrieval_top_k
    query_language = language or normalize.detect_language(text)

    rows = list(
        db.execute(
            select(QaKnowledgeExemplar)
            .where(
                QaKnowledgeExemplar.tenant_id == tenant_id,
                QaKnowledgeExemplar.status == "active",
            )
            .order_by(QaKnowledgeExemplar.created_at.desc())
            .limit(settings.qa_retrieval_candidate_cap)
        ).scalars()
    )
    if not rows:
        return []
    candidates = [
        {
            "id": row.id,
            "kind": row.kind,
            "title": row.title,
            "question": row.question,
            "answer": row.answer,
            "language": row.language,
            "search_text": row.search_text,
            "embedding": row.embedding,
        }
        for row in rows
    ]
    query_embedding = embed_text(text)
    return rank_candidates(
        candidates,
        query=text,
        query_language=query_language,
        query_embedding=query_embedding,
        top_k=limit,
    )
