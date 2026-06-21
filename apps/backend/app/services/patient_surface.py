"""Patient surface — the shared clinic→patient channel (AES-303/304/401/403).

One primitive ([foundation §4]): a tokenized, revocable share of a **curated** content snapshot.
The Basic payload (``report_aftercare``) carries selected sections + before/after media + aftercare.

The withholding contract (AES-403) is structural, not a filter: at create time only the explicitly
curated content is copied into ``PatientShare.content``, and the public read serves *that snapshot
alone*. Raw captures, internal notes, lots, national ID, and other visits are never copied, so they
cannot leak through the public endpoint. Sharing is an explicit staff action; the link is revocable
and may expire. The Pro Q&A payload is a later addition on the same primitive.
"""

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
    PatientShare,
    Session,
    Tenant,
)
from app.schemas.api import PatientShareCreate
from app.services.patients import get_patient
from app.services.reporting import report_template_context
from app.services.sessions import parse_uuid
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
        curated.append({"captureId": str(capture_uuid), "caption": caption.strip() if isinstance(caption, str) and caption.strip() else None})
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
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    treatments = metadata.get("treatments")
    if not isinstance(treatments, list):
        return []
    lines: list[str] = []
    for treatment in treatments:
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


def staff_share_payload(share: PatientShare, *, include_preview: bool = False) -> dict[str, Any]:
    """Serialize a share for staff (AES-403 per-share preview of exactly what the patient sees)."""
    content = share.content if isinstance(share.content, dict) else {}
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
    shares = db.execute(statement.order_by(PatientShare.created_at.desc())).scalars()
    return [staff_share_payload(share) for share in shares]


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
    return staff_share_payload(get_patient_share(db, principal.tenant_id, share_id), include_preview=True)


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
    if capture is None or capture.source_artifact_id is None:
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
