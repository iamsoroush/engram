"""Post-session patient Q&A routes (Pro payload of the patient surface; AES-402 / AES-403).

A self-contained router so the Q&A feature stays in mostly-new files: ``main.py`` only mounts it.
Public ``/qa/{token}`` endpoints take no auth (the token is the capability); staff ``/patient-qa/*``
endpoints follow the same role gates as the rest of the API. All logic lives in
``app/services/qa.py``; these handlers stay thin.
"""

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentPrincipal, staff_or_admin_required, staff_required
from app.db.session import get_db
from app.services import qa
from app.services.ai_jobs import require_ai_engine_token
from app.services.qa_knowledge import library as qa_library
from app.storage import ObjectStore, get_object_store

qa_api = APIRouter(prefix="/api/v1", tags=["patient-qa"])
# Trusted internal callbacks (the worker fetches the stored voice note); same gate as the AI job API.
qa_internal_api = APIRouter(prefix="/internal", dependencies=[Depends(require_ai_engine_token)], include_in_schema=False)


# --- Request bodies (camelCase in, like the rest of the API) ---------------------------------------


class QaThreadCreate(BaseModel):
    patient_id: str = Field(alias="patientId")
    model_config = {"populate_by_name": True}


class QaRouteRequest(BaseModel):
    doctor_user_id: str = Field(alias="doctorUserId")
    model_config = {"populate_by_name": True}


class QaSendRequest(BaseModel):
    # The approved reply text — the AI draft as-is, or the doctor's edit. Omit to send the draft.
    reply: str | None = None
    model_config = {"populate_by_name": True}


class QaRoutingModeUpdate(BaseModel):
    routing_mode: str = Field(alias="routingMode")
    model_config = {"populate_by_name": True}


class QaAskRequest(BaseModel):
    question: str


class QaTemplateBody(BaseModel):
    # A curated Q&A template: an optional title + question pattern + the approved answer (+ tags).
    title: str | None = None
    question: str | None = None
    answer: str
    tags: list[str] | None = None
    model_config = {"populate_by_name": True}


class QaSaveTemplateRequest(BaseModel):
    # "Save as template" from a sent reply — optional title; text is taken from the reply.
    title: str | None = None
    model_config = {"populate_by_name": True}


class QaExemplarStatusRequest(BaseModel):
    status: str  # "active" (re-include) | "excluded" (evict from the index)


# --- Staff: tenant Q&A routing policy (admin-configurable; foundation §7) --------------------------


@qa_api.get("/patient-qa/settings")
def qa_get_settings(
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return the tenant's Q&A routing policy."""
    return qa.qa_settings_payload(db, principal.tenant_id)


@qa_api.patch("/patient-qa/settings")
def qa_update_settings(
    request: QaRoutingModeUpdate,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Set the tenant's Q&A routing policy ('ai_default' | 'manual')."""
    return qa.set_qa_routing_mode(db, principal, request.routing_mode)


# --- Staff: threads + routing ----------------------------------------------------------------------


@qa_api.post("/patient-qa/threads")
def qa_create_thread(
    request: QaThreadCreate,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Open (or reuse) the Q&A channel for a patient; auto-routes per the tenant policy."""
    return qa.create_or_get_thread(db, principal, request.patient_id)


@qa_api.get("/patient-qa/threads")
def qa_list_threads(
    patient_id: str | None = Query(default=None, alias="patientId"),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List the tenant's Q&A threads, newest first (optionally one patient)."""
    return qa.list_threads(db, principal, patient_id=patient_id)


@qa_api.get("/patient-qa/threads/{thread_id}")
def qa_thread_detail(
    thread_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """One thread with its full message history + drafts + treating-doctor list (staff view)."""
    return qa.get_thread_detail(db, principal, thread_id)


@qa_api.post("/patient-qa/threads/{thread_id}/route")
def qa_route_thread(
    thread_id: str,
    request: QaRouteRequest,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Manually re-route a thread to one of the patient's treating doctors."""
    return qa.route_thread(db, principal, thread_id, request.doctor_user_id)


@qa_api.post("/patient-qa/threads/{thread_id}/revoke")
def qa_revoke_thread(
    thread_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Revoke a thread so its public link stops working (AES-403); idempotent."""
    return qa.revoke_thread(db, principal, thread_id)


@qa_api.get("/patient-qa/patients/{patient_id}/treating-doctors")
def qa_treating_doctors(
    patient_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """The patient's treating-doctor list (the manual re-route picker source)."""
    return qa.get_patient_treating_doctors(db, principal, patient_id)


# --- Staff: doctor inbox + reply/dismiss -----------------------------------------------------------


@qa_api.get("/patient-qa/inbox")
def qa_inbox(
    scope: str = Query(default="mine", pattern="^(mine|all)$"),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """The doctor Q&A inbox: pending questions + their AI-suggested replies."""
    return qa.qa_inbox(db, principal, scope=scope)


@qa_api.get("/patient-qa/inbox/summary")
def qa_inbox_summary(
    scope: str = Query(default="mine", pattern="^(mine|all)$"),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Lightweight pending/urgent counts for the top-bar Q&A badge + urgent toast (AES-1801)."""
    return qa.qa_inbox_summary(db, principal, scope=scope)


@qa_api.post("/patient-qa/messages/{message_id}/send")
def qa_send_reply(
    message_id: str,
    request: QaSendRequest,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Approve + send a reply to a patient question (doctor-verified). Nothing sends without this."""
    return qa.send_reply(db, principal, message_id, request.reply)


@qa_api.post("/patient-qa/messages/{message_id}/dismiss")
def qa_dismiss(
    message_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Dismiss a patient question without replying."""
    return qa.dismiss_question(db, principal, message_id)


@qa_api.post("/patient-qa/messages/{message_id}/voice-edit")
async def qa_voice_edit(
    message_id: str,
    file: UploadFile = File(...),
    draft: str = Form(default=""),
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store),
) -> dict[str, Any]:
    """Edit the reply with a spoken note; the AI decides whether it revises the draft or replaces it."""
    audio = await file.read()
    return qa.request_voice_edit(
        db,
        principal,
        object_store=object_store,
        message_id=message_id,
        audio=audio,
        content_type=file.content_type or "application/octet-stream",
        current_draft=draft,
    )


@qa_api.get("/patient-qa/messages/{message_id}/draft")
def qa_message_draft(
    message_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Poll the question's current draft state (used while a voice edit / initial draft runs)."""
    return qa.get_message_draft(db, principal, message_id)


# --- Staff: knowledge library (curated templates + auto-indexed sent replies; AES-410) -------------


@qa_api.get("/patient-qa/library")
def qa_library_list(
    kind: str | None = Query(default=None, pattern="^(template|sent_reply)$"),
    status_filter: str | None = Query(default=None, alias="status", pattern="^(active|excluded)$"),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """The Q&A knowledge library: curated templates + auto-indexed sent replies (with the exclude list)."""
    return qa_library.list_library(db, principal, kind=kind, status_filter=status_filter)


@qa_api.get("/patient-qa/library/{exemplar_id}")
def qa_library_item(
    exemplar_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """One exemplar's Q/A — the sent-reply provenance chip reveals its text (never the patient thread)."""
    return qa_library.get_library_item(db, principal, exemplar_id)


@qa_api.post("/patient-qa/library/templates")
def qa_library_create_template(
    request: QaTemplateBody,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a curated Q&A template (the clinic's standard guidance for a kind of question)."""
    return qa_library.create_template(
        db, principal, title=request.title, question=request.question, answer=request.answer, tags=request.tags
    )


@qa_api.patch("/patient-qa/library/templates/{exemplar_id}")
def qa_library_update_template(
    exemplar_id: str,
    request: QaTemplateBody,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Edit a curated template (templates only)."""
    return qa_library.update_template(
        db, principal, exemplar_id, title=request.title, question=request.question, answer=request.answer, tags=request.tags
    )


@qa_api.delete("/patient-qa/library/templates/{exemplar_id}", status_code=204)
def qa_library_delete_template(
    exemplar_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> Response:
    """Delete a curated template."""
    qa_library.delete_template(db, principal, exemplar_id)
    return Response(status_code=204)


@qa_api.post("/patient-qa/library/{exemplar_id}/status")
def qa_library_set_status(
    exemplar_id: str,
    request: QaExemplarStatusRequest,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Exclude (evict) or re-include an indexed exemplar — the manage/exclude list."""
    result = qa_library.set_exemplar_status(db, principal, exemplar_id, request.status)
    # Excluding an exemplar must retroactively drop it from any pending draft it grounded (Q-5) —
    # otherwise "exclude" implies a removal the draft doesn't deliver. Self-heal re-drafts without it.
    if request.status == "excluded":
        qa.invalidate_drafts_for_exemplar(db, tenant_id=principal.tenant_id, exemplar_id=exemplar_id)
        db.commit()
    return result


@qa_api.post("/patient-qa/messages/{message_id}/save-template")
def qa_save_reply_as_template(
    message_id: str,
    request: QaSaveTemplateRequest,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """"Save as template" from a sent doctor reply — the low-friction entry into the library."""
    return qa_library.save_reply_as_template(db, principal, message_id, title=request.title)


# --- Public patient surface (no auth — the token is the capability) --------------------------------


@qa_api.get("/qa/{token}")
def qa_public_thread(token: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """PUBLIC: the patient's own Q&A thread — their questions + doctor-verified replies only."""
    return qa.public_thread_payload(db, token)


@qa_api.post("/qa/{token}/ask")
def qa_public_ask(token: str, request: QaAskRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """PUBLIC: the patient asks a question; a reply draft is routed to the doctor's inbox."""
    return qa.ask_question(db, token, request.question)


# --- Internal (AI engine worker) -------------------------------------------------------------------


@qa_internal_api.get("/qa/voice/{job_id}")
def qa_internal_voice(
    job_id: str,
    db: Session = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store),
) -> Response:
    """INTERNAL: stream a qa_revise job's stored voice note to the worker."""
    payload = qa.internal_qa_voice_bytes(db, object_store=object_store, job_id=job_id)
    return Response(content=payload["content"], media_type=payload["media_type"])
