"""Q&A knowledge library: template CRUD, sent-reply auto-index, exclude list, and provenance.

The product surface behind the Library tab (AES-410): curated **templates** the clinic authors, plus
every doctor-approved sent reply **auto-indexed** by default with a one-tap exclude. All strictly
per-tenant. Kept free of any import of ``services.qa`` (which imports this module for auto-index +
retrieval) — it queries the models directly to avoid a cycle.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.auth.service import audit
from app.models import QaKnowledgeExemplar, QaMessage
from app.services.capabilities import POST_SESSION_QA, tenant_has_capability
from app.services.qa_knowledge import normalize
from app.services.qa_knowledge.embeddings import embed_text, embeddings_configured

KIND_TEMPLATE = "template"
KIND_SENT_REPLY = "sent_reply"

STATUS_ACTIVE = "active"
STATUS_EXCLUDED = "excluded"
_STATUSES = {STATUS_ACTIVE, STATUS_EXCLUDED}

MAX_TITLE_CHARS = 200
MAX_QUESTION_CHARS = 4000
MAX_ANSWER_CHARS = 8000
MAX_TAGS = 12
MAX_TAG_CHARS = 40
# Bound the patient-record / conversation snippet stored on a draft's provenance (AES-1903): enough to
# show the doctor what grounded the reply, not the whole report.
PROVENANCE_SNIPPET_CHARS = 500


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def require_qa_capability(db: DbSession, tenant_id: uuid.UUID) -> None:
    """Gate the library on the same Pro ``post_session_qa`` capability as the rest of Q&A."""
    if not tenant_has_capability(db, tenant_id, POST_SESSION_QA):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Post-session patient Q&A is a Pro feature.")


def _clean_tags(tags: list[str] | None) -> list[str]:
    """Normalize curator tags: trimmed, de-duplicated, bounded in count + length."""
    if not tags:
        return []
    seen: list[str] = []
    for tag in tags:
        value = " ".join(str(tag or "").split())[:MAX_TAG_CHARS].strip()
        if value and value not in seen:
            seen.append(value)
        if len(seen) >= MAX_TAGS:
            break
    return seen


def _maybe_embed(search_text: str) -> list[float] | None:
    """Compute an embedding for the row when a gateway is configured, else None (lexical-only)."""
    return embed_text(search_text)


def _refresh_lexical_and_embedding(exemplar: QaKnowledgeExemplar) -> None:
    """Recompute ``search_text`` (+ language) from the current title/question/answer and (re)embed it."""
    exemplar.search_text = normalize.build_search_text(
        title=exemplar.title, question=exemplar.question, answer=exemplar.answer
    )
    exemplar.language = normalize.detect_language(
        f"{exemplar.title or ''} {exemplar.question or ''} {exemplar.answer or ''}"
    )
    exemplar.embedding = _maybe_embed(exemplar.search_text)


# --- Serialization --------------------------------------------------------------------------------


def library_payload(exemplar: QaKnowledgeExemplar) -> dict[str, Any]:
    """Serialize one exemplar for the Library tab (staff view). Clinical CONTENT stays verbatim."""
    return {
        "id": str(exemplar.id),
        "kind": exemplar.kind,
        "status": exemplar.status,
        "title": exemplar.title,
        "question": exemplar.question,
        "answer": exemplar.answer,
        "language": exemplar.language,
        "tags": list(exemplar.tags or []),
        "sourceMessageId": str(exemplar.source_message_id) if exemplar.source_message_id else None,
        "indexed": exemplar.status == STATUS_ACTIVE,
        "createdAt": _iso(exemplar.created_at),
        "updatedAt": _iso(exemplar.updated_at),
    }


def list_library(
    db: DbSession,
    principal: CurrentPrincipal,
    *,
    kind: str | None = None,
    status_filter: str | None = None,
) -> dict[str, Any]:
    """List the tenant's exemplars for the Library tab (templates first, then indexed replies)."""
    require_qa_capability(db, principal.tenant_id)
    statement = select(QaKnowledgeExemplar).where(QaKnowledgeExemplar.tenant_id == principal.tenant_id)
    if kind in {KIND_TEMPLATE, KIND_SENT_REPLY}:
        statement = statement.where(QaKnowledgeExemplar.kind == kind)
    if status_filter in _STATUSES:
        statement = statement.where(QaKnowledgeExemplar.status == status_filter)
    rows = list(db.execute(statement.order_by(QaKnowledgeExemplar.created_at.desc())).scalars())
    templates = [library_payload(row) for row in rows if row.kind == KIND_TEMPLATE]
    sent_replies = [library_payload(row) for row in rows if row.kind == KIND_SENT_REPLY]
    return {
        "templates": templates,
        "sentReplies": sent_replies,
        "counts": {
            "templates": len(templates),
            "sentRepliesActive": sum(1 for row in rows if row.kind == KIND_SENT_REPLY and row.status == STATUS_ACTIVE),
            "sentRepliesExcluded": sum(1 for row in rows if row.kind == KIND_SENT_REPLY and row.status == STATUS_EXCLUDED),
        },
        # Whether hybrid semantic (embedding) matching is on. When False the library ranks lexical-only;
        # the UI shows one quiet notice so silent degradation (AES-1902) can't hide unconfigured embeddings.
        "semanticSearch": embeddings_configured(),
    }


def get_library_item(db: DbSession, principal: CurrentPrincipal, exemplar_id: str) -> dict[str, Any]:
    """One exemplar's Q/A (per-tenant) — the sent-reply provenance chip reveals its text, never a thread.

    The privacy boundary (AES-1903): a "پاسخ قبلی کلینیک" chip opens the exemplar's own question/answer,
    NOT the other patient's conversation. Serves the same ``library_payload`` shape as the list.
    """
    require_qa_capability(db, principal.tenant_id)
    return library_payload(_get_exemplar(db, principal.tenant_id, exemplar_id))


# --- Template CRUD (curated) ----------------------------------------------------------------------


def _get_exemplar(db: DbSession, tenant_id: uuid.UUID, exemplar_id: str) -> QaKnowledgeExemplar:
    exemplar = db.execute(
        select(QaKnowledgeExemplar).where(
            QaKnowledgeExemplar.id == _parse_uuid(exemplar_id),
            QaKnowledgeExemplar.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if exemplar is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Library item not found")
    return exemplar


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid id") from None


def create_template(
    db: DbSession,
    principal: CurrentPrincipal,
    *,
    title: str | None,
    question: str | None,
    answer: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Create a curated Q&A template (the clinic's standard guidance for a kind of question)."""
    require_qa_capability(db, principal.tenant_id)
    answer_text = (answer or "").strip()[:MAX_ANSWER_CHARS]
    if not answer_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A template answer is required")
    exemplar = QaKnowledgeExemplar(
        tenant_id=principal.tenant_id,
        kind=KIND_TEMPLATE,
        status=STATUS_ACTIVE,
        title=(title or "").strip()[:MAX_TITLE_CHARS] or None,
        question=(question or "").strip()[:MAX_QUESTION_CHARS] or None,
        answer=answer_text,
        tags=_clean_tags(tags),
        created_by_user_id=principal.user_id,
    )
    _refresh_lexical_and_embedding(exemplar)
    db.add(exemplar)
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="qa.library.template.create",
        target_type="qa_knowledge_exemplar",
        target_id=exemplar.id,
        details={},
    )
    db.commit()
    db.refresh(exemplar)
    return library_payload(exemplar)


def update_template(
    db: DbSession,
    principal: CurrentPrincipal,
    exemplar_id: str,
    *,
    title: str | None,
    question: str | None,
    answer: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Edit a curated template (templates only — auto-indexed replies are excluded, not edited)."""
    require_qa_capability(db, principal.tenant_id)
    exemplar = _get_exemplar(db, principal.tenant_id, exemplar_id)
    if exemplar.kind != KIND_TEMPLATE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only templates can be edited")
    answer_text = (answer or "").strip()[:MAX_ANSWER_CHARS]
    if not answer_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A template answer is required")
    exemplar.title = (title or "").strip()[:MAX_TITLE_CHARS] or None
    exemplar.question = (question or "").strip()[:MAX_QUESTION_CHARS] or None
    exemplar.answer = answer_text
    exemplar.tags = _clean_tags(tags)
    _refresh_lexical_and_embedding(exemplar)
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="qa.library.template.update",
        target_type="qa_knowledge_exemplar",
        target_id=exemplar.id,
        details={},
    )
    db.commit()
    db.refresh(exemplar)
    return library_payload(exemplar)


def delete_template(db: DbSession, principal: CurrentPrincipal, exemplar_id: str) -> None:
    """Delete a curated template. Auto-indexed replies are managed via exclude, not deletion."""
    require_qa_capability(db, principal.tenant_id)
    exemplar = _get_exemplar(db, principal.tenant_id, exemplar_id)
    if exemplar.kind != KIND_TEMPLATE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only templates can be deleted")
    db.delete(exemplar)
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="qa.library.template.delete",
        target_type="qa_knowledge_exemplar",
        target_id=exemplar.id,
        details={},
    )
    db.commit()


def set_exemplar_status(db: DbSession, principal: CurrentPrincipal, exemplar_id: str, new_status: str) -> dict[str, Any]:
    """Exclude (evict) or re-include an indexed exemplar — the manage/exclude list (AES-410)."""
    require_qa_capability(db, principal.tenant_id)
    if new_status not in _STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported status")
    exemplar = _get_exemplar(db, principal.tenant_id, exemplar_id)
    exemplar.status = new_status
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="qa.library.exemplar.status",
        target_type="qa_knowledge_exemplar",
        target_id=exemplar.id,
        details={"status": new_status},
    )
    db.commit()
    db.refresh(exemplar)
    return library_payload(exemplar)


def save_reply_as_template(
    db: DbSession, principal: CurrentPrincipal, message_id: str, *, title: str | None
) -> dict[str, Any]:
    """"Save as template" from a sent doctor reply — copy its text into a curated template.

    The low-friction entry into the library: a good reply becomes reusable guidance in one tap. The
    template's question is the patient question it answered; its answer is the reply text.
    """
    require_qa_capability(db, principal.tenant_id)
    reply = db.execute(
        select(QaMessage).where(
            QaMessage.id == _parse_uuid(message_id),
            QaMessage.tenant_id == principal.tenant_id,
            QaMessage.role == "doctor",
        )
    ).scalar_one_or_none()
    if reply is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sent reply not found")
    question_text: str | None = None
    if reply.in_reply_to_id is not None:
        question = db.get(QaMessage, reply.in_reply_to_id)
        question_text = question.body if question is not None else None
    return create_template(
        db,
        principal,
        title=title,
        question=question_text,
        answer=reply.body,
        tags=None,
    )


# --- Sent-reply auto-index (called from qa.send_reply) --------------------------------------------


def auto_index_sent_reply(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    question_text: str | None,
    reply_text: str,
    source_message_id: uuid.UUID,
    doctor_user_id: uuid.UUID | None,
) -> None:
    """Index a doctor-approved sent reply into the tenant's knowledge base (idempotent, best-effort).

    Every approved reply is trusted clinical communication, so it enters the index automatically
    (AES-410 · Q3), retrievable by default with a one-tap exclude. Idempotent on ``source_message_id``
    (a re-send / recovery never double-indexes). Best-effort: a failure here must never break sending
    the reply — the caller does not depend on the return value and this runs inside the send transaction
    (a duplicate is skipped, not raised).
    """
    answer = (reply_text or "").strip()
    if not answer:
        return
    existing = db.execute(
        select(QaKnowledgeExemplar).where(
            QaKnowledgeExemplar.tenant_id == tenant_id,
            QaKnowledgeExemplar.source_message_id == source_message_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    exemplar = QaKnowledgeExemplar(
        tenant_id=tenant_id,
        kind=KIND_SENT_REPLY,
        status=STATUS_ACTIVE,
        title=None,
        question=(question_text or "").strip()[:MAX_QUESTION_CHARS] or None,
        answer=answer[:MAX_ANSWER_CHARS],
        tags=[],
        source_message_id=source_message_id,
        created_by_user_id=doctor_user_id,
    )
    _refresh_lexical_and_embedding(exemplar)
    db.add(exemplar)


# --- Provenance (the "based on: …" chip) ----------------------------------------------------------


def provenance_from_exemplars(exemplars: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The doctor-only provenance for a draft: the TOP retrieved exemplar (or None if nothing found).

    Shaped ``{kind, exemplarId, label}`` — ``label`` is the template title for a template, else None
    (the UI renders "a previous reply" for a sent reply). Similarity scores stay internal (Q5): the
    chip is attribution, not a number.
    """
    if not exemplars:
        return None
    top = exemplars[0]
    return {
        "kind": top.get("kind"),
        "exemplarId": top.get("exemplarId"),
        "label": top.get("title") if top.get("kind") == KIND_TEMPLATE else None,
    }


def build_draft_provenance(
    *,
    exemplars: list[dict[str, Any]],
    patient_context: dict[str, Any] | None,
    thread_history: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """The structured «بر اساس» provenance panel (AES-1903): every source the payload actually carried.

    Deterministic — built by the backend from what it put in the qa_draft payload (no prompt/eval
    change). Shaped::

        {
          "grounded": bool,               # False => the honest "general knowledge, no clinical source"
          "sources": [ {"type": "template"|"sent_reply"|"patient_aftercare"|"patient_summary"|"conversation",
                        "exemplarId"?: str, "label"?: str}, ... ],
          # backward-compatible top-level attribution (the strong "based on" chip + exemplar invalidation):
          "kind"?, "exemplarId"?, "label"?
        }

    The top exemplar keeps the strong "grounded on" attribution (template title / a previous reply);
    patient-record + conversation add context chips; an empty ``sources`` is the general-knowledge
    caution state. Similarity scores stay internal — the chips are attribution, not numbers.
    """
    ctx = patient_context or {}
    sources: list[dict[str, Any]] = []
    top = exemplars[0] if exemplars else None
    if top is not None:
        if top.get("kind") == KIND_TEMPLATE:
            sources.append({"type": "template", "exemplarId": top.get("exemplarId"), "label": top.get("title")})
        else:
            sources.append({"type": "sent_reply", "exemplarId": top.get("exemplarId")})
    # Patient-record + conversation chips carry a bounded snippet of the ACTUAL grounding text so the
    # doctor can tap to see what informed the draft (AES-1903). It is THIS patient's own data (no
    # cross-patient leak); the exemplar chips carry only an id and fetch their Q/A on demand.
    if isinstance(ctx.get("recentAftercare"), str) and ctx["recentAftercare"].strip():
        sources.append({"type": "patient_aftercare", "text": ctx["recentAftercare"].strip()[:PROVENANCE_SNIPPET_CHARS]})
    recent_summaries = ctx.get("recentVisitSummaries") or []
    memory_summary = ctx.get("memorySummary")
    summary_text = str(recent_summaries[0] if recent_summaries else (memory_summary or "")).strip()
    if summary_text:
        sources.append({"type": "patient_summary", "text": summary_text[:PROVENANCE_SNIPPET_CHARS]})
    if thread_history:
        turn = thread_history[-1] if isinstance(thread_history[-1], dict) else {}
        convo = f"Q: {turn.get('question', '')}\nA: {turn.get('answer', '')}".strip()
        sources.append({"type": "conversation", "text": convo[:PROVENANCE_SNIPPET_CHARS]})

    provenance: dict[str, Any] = {"grounded": bool(sources), "sources": sources}
    if top is not None:
        # Keep the legacy top-level attribution so the strong chip + Q-5 exemplar invalidation keep working.
        provenance["kind"] = top.get("kind")
        provenance["exemplarId"] = top.get("exemplarId")
        provenance["label"] = top.get("title") if top.get("kind") == KIND_TEMPLATE else None
    return provenance
