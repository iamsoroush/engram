"""Patient surface — the shared clinic→patient channel (AES-303/304/401/403).

One primitive ([foundation §4]): a tokenized, revocable share of a **curated** content snapshot.
The Basic payload (``report_aftercare``) carries selected sections + before/after media + aftercare.

The withholding contract (AES-403) is structural, not a filter: at create time only the explicitly
curated content is copied into ``PatientShare.content``, and the public read serves *that snapshot
alone*. Raw captures, internal notes, lots, national ID, and other visits are never copied, so they
cannot leak through the public endpoint. Sharing is an explicit staff action; the link is revocable
and may expire. The Pro Q&A payload is a later addition on the same primitive.
"""

import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.auth.service import audit
from app.models import (
    AftercareTemplate,
    Artifact,
    Capture,
    CaptureStatus,
    CaptureType,
    Patient,
    PatientShare,
    Session,
    Tenant,
)
from app.schemas.shares import PatientShareCreate
from app.services.patients import get_patient
from app.services.reporting import report_template_context
from app.services.sessions import parse_uuid
from app.services.treatment_overlay import performed_treatments
from app.storage import ObjectStore

SHARE_SCHEMA_VERSION = "2026-06-12.patient-share.v1"
SHARE_STATUS_ACTIVE = "active"
SHARE_STATUS_REVOKED = "revoked"
BASIC_PAYLOAD_TYPE = "report_aftercare"
MAX_SHARE_SECTIONS = 30
MAX_SHARE_MEDIA = 60


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _is_expired(share: PatientShare) -> bool:
    if share.expires_at is None:
        return False
    expires_at = share.expires_at if share.expires_at.tzinfo else share.expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= _utc_now()


def _is_publicly_readable(share: PatientShare) -> bool:
    return share.status == SHARE_STATUS_ACTIVE and not _is_expired(share)


def _effective_status(share: PatientShare) -> str:
    if share.status == SHARE_STATUS_REVOKED:
        return SHARE_STATUS_REVOKED
    if _is_expired(share):
        return "expired"
    return SHARE_STATUS_ACTIVE


# Lot/batch tokens must never reach the patient (the withholding contract, `patient-surface.md`).
# The AI caption is *mandated* to read lot/batch numbers, and the share sheet prefills captions with
# it, so the caption channel is filtered server-side at snapshot time (Q-6). Two shapes are removed:
# a labelled lot ("lot A1234B", «سری ساخت ۱۲۳») and a bare lot-like code (a single token mixing
# letters and digits, ≥5 chars — e.g. A1234B), which spares plain words, dates, and split doses.
_LOT_LABEL_RE = re.compile(
    r"\b(?:lot|batch|lot\s*no|batch\s*no|lot\s*#|batch\s*#)\b\.?\s*[:#]?\s*[A-Za-z0-9][A-Za-z0-9\-/]*",
    re.IGNORECASE,
)
_LOT_LABEL_FA_RE = re.compile(r"(?:لات|بچ|سری\s*ساخت|شماره\s*سری)\s*[:#]?\s*[\w\-/]+")
_LOT_BARE_RE = re.compile(r"\b(?=[A-Za-z0-9\-]*[A-Za-z])(?=[A-Za-z0-9\-]*\d)[A-Za-z0-9\-]{5,}\b")


def _strip_lot_tokens(text: str | None) -> str | None:
    """Remove lot/batch tokens from a free-text caption (Q-6). Returns None when nothing survives."""
    if not isinstance(text, str) or not text.strip():
        return None
    cleaned = _LOT_LABEL_RE.sub("", text)
    cleaned = _LOT_LABEL_FA_RE.sub("", cleaned)
    cleaned = _LOT_BARE_RE.sub("", cleaned)
    # Tidy the punctuation/space left behind by removals (e.g. "vial, lot A1234B" → "vial").
    cleaned = re.sub(r"\s*[,،؛;]\s*(?=[,،؛;]|$)", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,،؛;-–—")
    return cleaned or None


def _curated_media(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    media: list[Any],
) -> list[dict[str, Any]]:
    """Validate and snapshot curated media refs, withholding anything not the patient's own photo."""
    if not media:
        return []
    if len(media) > MAX_SHARE_MEDIA:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Too many media items in the share")
    requested: dict[uuid.UUID, str | None] = {}
    for item in media:
        try:
            capture_uuid = uuid.UUID(item.capture_id)
        except (ValueError, AttributeError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid media captureId") from exc
        requested.setdefault(capture_uuid, item.caption)
    captures = db.execute(
        select(Capture).where(
            Capture.id.in_(list(requested.keys())),
            Capture.tenant_id == tenant_id,
            Capture.capture_type == CaptureType.photo,
            Capture.status != CaptureStatus.deleted,
            Capture.source_artifact_id.is_not(None),
        )
    ).scalars().all()
    found = {capture.id: capture for capture in captures}
    # Map each capture to the patient it belongs to (directly or via its session) so the share can
    # only ever include THIS patient's photos.
    session_patient: dict[uuid.UUID, uuid.UUID | None] = {}
    session_ids = {capture.session_id for capture in captures if capture.patient_id is None}
    if session_ids:
        for sid, pid in db.execute(
            select(Session.id, Session.patient_id).where(
                Session.tenant_id == tenant_id, Session.id.in_(list(session_ids))
            )
        ).all():
            session_patient[sid] = pid
    curated: list[dict[str, Any]] = []
    for capture_uuid, caption in requested.items():
        capture = found.get(capture_uuid)
        if capture is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Media capture {capture_uuid} not found")
        owner = capture.patient_id or session_patient.get(capture.session_id)
        if owner != patient_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A selected photo does not belong to this patient",
            )
        # Filter lot/batch tokens out of the (AI-prefilled) caption at snapshot time (Q-6).
        curated.append({"captureId": str(capture_uuid), "caption": _strip_lot_tokens(caption)})
    return curated


def _curated_aftercare(db: DbSession, *, tenant_id: uuid.UUID, aftercare: Any) -> dict[str, Any] | None:
    """Resolve the aftercare block — snapshot a template by id, or take inline name+body."""
    if aftercare is None:
        return None
    if aftercare.template_id:
        template = db.execute(
            select(AftercareTemplate).where(
                AftercareTemplate.id == parse_uuid(aftercare.template_id, "aftercare.templateId"),
                AftercareTemplate.tenant_id == tenant_id,
            )
        ).scalar_one_or_none()
        if template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aftercare template not found")
        return {
            "templateId": str(template.id),
            "name": (aftercare.name or template.name).strip(),
            "body": (aftercare.body if aftercare.body is not None else template.body),
        }
    if aftercare.body is not None and aftercare.body.strip():
        return {"templateId": None, "name": (aftercare.name or "Aftercare instructions").strip(), "body": aftercare.body}
    return None


def _curated_sections(sections: list[Any]) -> list[dict[str, str]]:
    if len(sections) > MAX_SHARE_SECTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Too many sections in the share")
    curated: list[dict[str, str]] = []
    for section in sections:
        label = (section.label or "").strip()
        body = (section.body or "").strip()
        if not body:
            continue
        curated.append({"label": label, "body": body})
    return curated


def _curated_treatment_lines(session: Session | None, *, include_brands: bool) -> list[str]:
    """Plain-words 'what we did' lines from a session's treatments (Story C, decision 2).

    Generic by default — `area — product(category)`; the commercial `brand` is appended ONLY when the
    clinic opted in. Dose/quantity and lot are NEVER included (the dose table + lots are
    always-withheld; this is the patient-safe plain-words line, not the clinical record).
    """
    if session is None:
        return []
    # Read the OVERLAID treatments (M-P4): a clinician-corrected area/product/brand must reach the
    # patient-facing "what we did" lines, not the raw AI artifact (the AES-1101 safety class).
    lines: list[str] = []
    for treatment in performed_treatments(session):
        if not isinstance(treatment, dict):
            continue
        area = str(treatment.get("area") or "").strip()
        product = str(treatment.get("product") or "").strip()
        brand = str(treatment.get("brand") or "").strip()
        head = " — ".join(part for part in (area, product) if part)
        if not head:
            continue
        lines.append(f"{head} ({brand})" if include_brands and brand else head)
    return lines


def create_patient_share(db: DbSession, principal: CurrentPrincipal, request: PatientShareCreate) -> dict[str, Any]:
    """Create a tokenized, revocable share of curated content (AES-303/304/403).

    Validates the patient, optional source visit, curated media (must be the patient's own photos),
    and aftercare, then freezes them into an immutable content snapshot under a fresh unguessable
    token. Returns the staff payload including the token and the public path.
    """
    patient = get_patient(db, principal.tenant_id, request.patient_id)
    session: Session | None = None
    if request.session_id:
        session = db.execute(
            select(Session).where(
                Session.id == parse_uuid(request.session_id, "session_id"),
                Session.tenant_id == principal.tenant_id,
            )
        ).scalar_one_or_none()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        if session.patient_id is not None and session.patient_id != patient.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session belongs to a different patient")

    clinic = report_template_context(session.report_template_key if session else None)["clinic"]
    tenant = db.get(Tenant, principal.tenant_id)
    include_brands = bool(tenant and tenant.share_include_brands)
    content = {
        "schemaVersion": SHARE_SCHEMA_VERSION,
        "clinicName": clinic["name"],
        "patientName": patient.display_name,
        "title": (request.title or "Your visit summary").strip(),
        "visitDate": _iso(session.captured_at) if session and session.captured_at else None,
        # The clinic's report language, so the public page localizes its chrome to match the content.
        "language": (tenant.report_language if tenant else None),
        "sections": _curated_sections(request.sections),
        "treatments": _curated_treatment_lines(session, include_brands=include_brands) if request.include_treatments else [],
        "media": _curated_media(db, tenant_id=principal.tenant_id, patient_id=patient.id, media=request.media),
        "aftercare": _curated_aftercare(db, tenant_id=principal.tenant_id, aftercare=request.aftercare),
    }

    expires_at = _utc_now() + timedelta(days=request.expires_in_days) if request.expires_in_days else None
    share = PatientShare(
        tenant_id=principal.tenant_id,
        patient_id=patient.id,
        session_id=session.id if session else None,
        token=secrets.token_urlsafe(32),
        payload_type=BASIC_PAYLOAD_TYPE,
        status=SHARE_STATUS_ACTIVE,
        content=content,
        created_by_user_id=principal.user_id,
        expires_at=expires_at,
    )
    db.add(share)
    db.flush()
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="patient_share.create",
        target_type="patient_share",
        target_id=share.id,
        details={"patient_id": str(patient.id), "session_id": str(session.id) if session else None, "media_count": len(content["media"])},
    )
    db.commit()
    db.refresh(share)
    return staff_share_payload(share, include_preview=True)


def _share_is_stale(share: PatientShare, source_updated_at: datetime | None) -> bool:
    """Whether an active share predates its source visit's latest change (Q-4).

    The snapshot is immutable by design, so a later report correction or safety-flag addition on the
    source visit leaves the share showing outdated content. This surfaces that (needs-attention),
    computed lazily from ``session.updated_at`` rather than stored — no correction-site write."""
    if not _is_publicly_readable(share) or source_updated_at is None or share.created_at is None:
        return False
    created = share.created_at if share.created_at.tzinfo else share.created_at.replace(tzinfo=timezone.utc)
    changed = source_updated_at if source_updated_at.tzinfo else source_updated_at.replace(tzinfo=timezone.utc)
    return changed > created


def staff_share_payload(
    share: PatientShare,
    *,
    include_preview: bool = False,
    source_updated_at: datetime | None = None,
) -> dict[str, Any]:
    """Serialize a share for staff (AES-403 per-share preview of exactly what the patient sees).

    ``source_updated_at`` (the share's source visit's latest change time) drives the ``stale`` /
    ``staleSince`` needs-attention flags (Q-4); pass it whenever the source session is loaded."""
    content = share.content if isinstance(share.content, dict) else {}
    stale = _share_is_stale(share, source_updated_at)
    payload = {
        "id": str(share.id),
        "tenantId": str(share.tenant_id),
        "patientId": str(share.patient_id),
        "sessionId": str(share.session_id) if share.session_id else None,
        "token": share.token,
        "publicPath": f"/share/{share.token}",
        "payloadType": share.payload_type,
        "status": _effective_status(share),
        "title": content.get("title"),
        "mediaCount": len(content.get("media", []) if isinstance(content.get("media"), list) else []),
        # Needs-attention (Q-4): the source visit changed after this share was frozen — staff should
        # review/re-share. Only ever True for an active, publicly-readable share.
        "stale": stale,
        "staleSince": _iso(source_updated_at) if stale else None,
        "createdAt": _iso(share.created_at),
        "updatedAt": _iso(share.updated_at),
        "expiresAt": _iso(share.expires_at),
        "revokedAt": _iso(share.revoked_at),
    }
    if include_preview:
        payload["preview"] = _public_content(share)
    return payload


def list_patient_shares(db: DbSession, principal: CurrentPrincipal, *, patient_id: str | None = None) -> list[dict[str, Any]]:
    """List the tenant's shares, optionally scoped to one patient, newest first."""
    statement = select(PatientShare).where(PatientShare.tenant_id == principal.tenant_id)
    if patient_id:
        statement = statement.where(PatientShare.patient_id == parse_uuid(patient_id, "patient_id"))
    shares = list(db.execute(statement.order_by(PatientShare.created_at.desc())).scalars())
    # Batch-load each source visit's latest-change time to flag stale (predates a correction) shares.
    session_ids = {share.session_id for share in shares if share.session_id is not None}
    source_updated: dict[uuid.UUID, datetime] = {}
    if session_ids:
        for sid, updated_at in db.execute(
            select(Session.id, Session.updated_at).where(
                Session.tenant_id == principal.tenant_id, Session.id.in_(list(session_ids))
            )
        ).all():
            source_updated[sid] = updated_at
    return [staff_share_payload(share, source_updated_at=source_updated.get(share.session_id)) for share in shares]


def get_patient_share(db: DbSession, tenant_id: uuid.UUID, share_id: str) -> PatientShare:
    """Load a tenant's share or raise 404."""
    share = db.execute(
        select(PatientShare).where(
            PatientShare.id == parse_uuid(share_id, "share_id"),
            PatientShare.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share not found")
    return share


def get_patient_share_payload(db: DbSession, principal: CurrentPrincipal, share_id: str) -> dict[str, Any]:
    """Return one share with its full curated preview for staff review."""
    share = get_patient_share(db, principal.tenant_id, share_id)
    source_updated_at = None
    if share.session_id is not None:
        source_updated_at = db.execute(
            select(Session.updated_at).where(
                Session.id == share.session_id, Session.tenant_id == principal.tenant_id
            )
        ).scalar_one_or_none()
    return staff_share_payload(share, include_preview=True, source_updated_at=source_updated_at)


def revoke_patient_share(db: DbSession, principal: CurrentPrincipal, share_id: str) -> dict[str, Any]:
    """Revoke a share so its public link stops working (AES-403)."""
    share = get_patient_share(db, principal.tenant_id, share_id)
    if share.status != SHARE_STATUS_REVOKED:
        share.status = SHARE_STATUS_REVOKED
        share.revoked_at = _utc_now()
        share.revoked_by_user_id = principal.user_id
        audit(
            db,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            action="patient_share.revoke",
            target_type="patient_share",
            target_id=share.id,
            details={},
        )
        db.commit()
        db.refresh(share)
    return staff_share_payload(share)


def _revoke_shares(
    db: DbSession,
    shares: list[PatientShare],
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    reason: str,
) -> int:
    """Revoke the given active shares (shared body for reassignment/archive revocation)."""
    now = _utc_now()
    revoked = 0
    for share in shares:
        if share.status == SHARE_STATUS_REVOKED:
            continue
        share.status = SHARE_STATUS_REVOKED
        share.revoked_at = now
        share.revoked_by_user_id = actor_user_id
        revoked += 1
        audit(
            db,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="patient_share.revoke",
            target_type="patient_share",
            target_id=share.id,
            details={"reason": reason},
        )
    return revoked


def revoke_shares_for_session(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    session_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
    reason: str = "reassignment",
) -> int:
    """Auto-revoke every active share frozen from a session (M-P3/Q-4).

    Called when the session's patient changes (reassignment/de-effect): a share froze the visit's
    sections + photos + patient name into an immutable snapshot under a live token, so after A→B the
    public link would keep serving B's content under A's name. Hard-revoke closes that. The caller
    commits. Returns how many shares were revoked."""
    shares = list(
        db.execute(
            select(PatientShare).where(
                PatientShare.tenant_id == tenant_id,
                PatientShare.session_id == session_id,
                PatientShare.status == SHARE_STATUS_ACTIVE,
            )
        ).scalars()
    )
    return _revoke_shares(db, shares, tenant_id=tenant_id, actor_user_id=actor_user_id, reason=reason)


def revoke_patient_shares_on_archive(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
) -> int:
    """Revoke a patient's active shares when the patient is archived (Q-9 archive half). Caller commits."""
    shares = list(
        db.execute(
            select(PatientShare).where(
                PatientShare.tenant_id == tenant_id,
                PatientShare.patient_id == patient_id,
                PatientShare.status == SHARE_STATUS_ACTIVE,
            )
        ).scalars()
    )
    return _revoke_shares(db, shares, tenant_id=tenant_id, actor_user_id=actor_user_id, reason="patient_archived")


def _public_content(share: PatientShare) -> dict[str, Any]:
    """Project the stored snapshot into the read-only patient-facing payload (curated only)."""
    content = share.content if isinstance(share.content, dict) else {}
    media = content.get("media") if isinstance(content.get("media"), list) else []
    return {
        "schemaVersion": SHARE_SCHEMA_VERSION,
        "payloadType": share.payload_type,
        "status": _effective_status(share),
        "clinic": {"name": content.get("clinicName")},
        "patientName": content.get("patientName"),
        "title": content.get("title"),
        "visitDate": content.get("visitDate"),
        "language": content.get("language"),
        "sections": content.get("sections") if isinstance(content.get("sections"), list) else [],
        "treatments": content.get("treatments") if isinstance(content.get("treatments"), list) else [],
        "media": [
            {
                "captureId": item.get("captureId"),
                "caption": item.get("caption"),
                "url": f"/api/v1/share/{share.token}/media/{item.get('captureId')}",
            }
            for item in media
            if isinstance(item, dict) and item.get("captureId")
        ],
        "aftercare": content.get("aftercare"),
        "createdAt": _iso(share.created_at),
        "expiresAt": _iso(share.expires_at),
    }


def _share_by_token(db: DbSession, token: str) -> PatientShare:
    """Resolve an active, unexpired share by token, or 404 (no info leak on revoked/expired)."""
    share = db.execute(select(PatientShare).where(PatientShare.token == token)).scalar_one_or_none()
    if share is None or not _is_publicly_readable(share):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This link is not available")
    return share


def public_share_payload(db: DbSession, token: str) -> dict[str, Any]:
    """PUBLIC: return the read-only curated payload for a share token (AES-401)."""
    return _public_content(_share_by_token(db, token))


def public_share_media(db: DbSession, *, object_store: ObjectStore, token: str, capture_id: str) -> dict[str, Any]:
    """PUBLIC: stream a curated photo for a share, only if it is in the share's media list."""
    share = _share_by_token(db, token)
    content = share.content if isinstance(share.content, dict) else {}
    media_ids = {
        item.get("captureId")
        for item in (content.get("media") if isinstance(content.get("media"), list) else [])
        if isinstance(item, dict)
    }
    if capture_id not in media_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    capture = db.execute(
        select(Capture).where(
            Capture.id == parse_uuid(capture_id, "capture_id"),
            Capture.tenant_id == share.tenant_id,
        )
    ).scalar_one_or_none()
    if capture is None or capture.source_artifact_id is None or capture.status == CaptureStatus.deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    # Q-4: re-check patient OWNERSHIP at read time, not just tenant. A photo shared under patient A's
    # token whose visit was later reassigned to B (or whose capture was reassigned) must stop
    # streaming — otherwise B's photo keeps serving under A's link even after reassignment.
    owner = capture.patient_id
    if owner is None and capture.session_id is not None:
        owner = db.execute(
            select(Session.patient_id).where(
                Session.id == capture.session_id, Session.tenant_id == share.tenant_id
            )
        ).scalar_one_or_none()
    if owner != share.patient_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    artifact = db.execute(
        select(Artifact).where(Artifact.id == capture.source_artifact_id, Artifact.tenant_id == share.tenant_id)
    ).scalar_one_or_none()
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    return {
        "content": object_store.get_object_bytes(artifact.object_key),
        "media_type": artifact.mime_type or "application/octet-stream",
        "filename": (capture.capture_metadata or {}).get("original_filename") or f"{capture.id}",
    }
