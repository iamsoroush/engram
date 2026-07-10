import copy
import hashlib
import io
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.auth.service import audit
from app.config import settings
from app.models import (
    Artifact,
    ArtifactKind,
    Capture,
    CaptureStatus,
    CaptureType,
    OrganizationSource,
    Patient,
    Session,
    SessionStatus,
)
from app.observability.metrics import record_capture_upload_failed
from app.services.reporting import patient_information_from_assignment, render_report_body_markdown, report_template_context
from app.services.patient_memory_intelligence import mark_patient_memory_updating
from app.services.session_contracts import build_session_contracts, evolve_session_after_capture, session_is_complete
from app.storage import ObjectStore


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def object_key_for_source(tenant_id: uuid.UUID, session_id: uuid.UUID, capture_id: uuid.UUID, artifact_id: uuid.UUID) -> str:
    return f"tenants/{tenant_id}/sessions/{session_id}/captures/{capture_id}/source/{artifact_id}"


def note_detail_with_file_fallback(detail: str, content: bytes) -> str:
    """A note's text travels in metadata `detail` — the uploaded file is only a mirror.

    The synthesis context reads ONLY `metadata.detail` for notes, so an API client that sends just
    the file would get a silently hollow report. When `detail` is empty, derive it from the file's
    UTF-8 text (non-decodable content leaves detail as given).
    """
    if detail.strip():
        return detail
    try:
        return content.decode("utf-8").strip()
    except UnicodeDecodeError:
        return detail


def validate_wav_pcm_16k_mono(content: bytes) -> None:
    if len(content) < 44 or content[0:4] != b"RIFF" or content[8:12] != b"WAVE":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Audio must be WAV PCM 16-bit mono 16kHz")

    offset = 12
    fmt_seen = False
    data_seen = False
    while offset + 8 <= len(content):
        chunk_id = content[offset : offset + 4]
        chunk_size = int.from_bytes(content[offset + 4 : offset + 8], "little")
        chunk_start = offset + 8
        chunk_end = chunk_start + chunk_size
        if chunk_end > len(content):
            break
        if chunk_id == b"fmt ":
            if chunk_size < 16:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid WAV fmt chunk")
            audio_format = int.from_bytes(content[chunk_start : chunk_start + 2], "little")
            channels = int.from_bytes(content[chunk_start + 2 : chunk_start + 4], "little")
            sample_rate = int.from_bytes(content[chunk_start + 4 : chunk_start + 8], "little")
            bits_per_sample = int.from_bytes(content[chunk_start + 14 : chunk_start + 16], "little")
            if audio_format != 1 or channels != 1 or sample_rate != 16000 or bits_per_sample != 16:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Audio must be WAV PCM 16-bit mono 16kHz")
            fmt_seen = True
        if chunk_id == b"data" and chunk_size > 0:
            data_seen = True
        offset = chunk_end + (chunk_size % 2)

    if not fmt_seen or not data_seen:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Audio must include WAV fmt and data chunks")


def get_session_for_tenant(
    db: DbSession, tenant_id: uuid.UUID, session_id: uuid.UUID, *, for_update: bool = False
) -> Session:
    """Fetch a tenant-scoped session. ``for_update`` takes a row lock (INV-LOCK, S-F15) so a user-state
    write serializes against the synthesis completion handler's read-modify-write of the same
    ``extracted_metadata`` JSON column (no-op on SQLite, which ignores ``FOR UPDATE``)."""
    query = select(Session).where(Session.id == session_id, Session.tenant_id == tenant_id)
    if for_update:
        query = query.with_for_update()
    session = db.execute(query).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


def _report_model_with_media_pairing(
    structured_report: dict[str, Any], db: DbSession, session: Session
) -> dict[str, Any]:
    """Attach each ``media`` image block's capture ``photo_pairing`` to the serialized report model.

    The deterministic before/after pairing lives on the photo capture (``recompute_session_photo_pairing``).
    Carrying it on the report's image blocks lets the client render the before/after **slider** directly
    — "the rendering consumes pairs, it does not pair" (redesign-pro-report §2.4) — without an extra
    fetch per photo. Returns a deep copy when anything is attached, so the ORM JSONB is never mutated.
    """
    sections = structured_report.get("sections")
    if not isinstance(sections, list):
        return structured_report
    image_capture_ids: set[str] = set()
    for section in sections:
        if not isinstance(section, dict):
            continue
        for block in section.get("blocks") or []:
            if isinstance(block, dict) and block.get("type") == "image" and block.get("captureId"):
                image_capture_ids.add(str(block["captureId"]))
    parsed_ids = []
    for capture_id in image_capture_ids:
        try:
            parsed_ids.append(uuid.UUID(capture_id))
        except ValueError:
            continue
    if not parsed_ids:
        return structured_report
    pairing_by_capture: dict[str, dict[str, Any]] = {}
    for capture in db.execute(
        select(Capture).where(Capture.tenant_id == session.tenant_id, Capture.id.in_(parsed_ids))
    ).scalars():
        pairing = (capture.capture_metadata or {}).get("photo_pairing")
        if isinstance(pairing, dict):
            pairing_by_capture[str(capture.id)] = pairing
    if not pairing_by_capture:
        return structured_report
    enriched = copy.deepcopy(structured_report)
    for section in enriched.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for block in section.get("blocks") or []:
            if isinstance(block, dict) and block.get("type") == "image":
                pairing = pairing_by_capture.get(str(block.get("captureId")))
                if pairing is not None:
                    block["pairing"] = pairing
    return enriched


def session_payload(session: Session, db: DbSession | None = None) -> dict[str, Any]:
    from app.services.attribution import attribution_payload
    from app.services.treatment_overlay import effective_treatments_from_metadata

    contracts = build_session_contracts(session, db)
    extracted_metadata = session.extracted_metadata or {}
    # (S-F8) Fold the user-authored treatment overlay into the treatments the payload exposes — the
    # capture screen's treatment table reads `extractedMetadata.treatments`, so a corrected lot/dose must
    # show here too (not just in recall / smart-lists / memory, which already read effective_treatments).
    # A read-only projection: the raw AI artifact stays untouched in the DB; identity when no overlay.
    if isinstance(extracted_metadata, dict) and isinstance(extracted_metadata.get("treatments"), list):
        extracted_metadata = {**extracted_metadata, "treatments": effective_treatments_from_metadata(extracted_metadata)}
    assignment_source = extracted_metadata.get("patient_assignment_source")
    structured_report = session.report_model if isinstance(session.report_model, dict) and session.report_model else None
    if structured_report is not None and db is not None:
        structured_report = _report_model_with_media_pairing(structured_report, db, session)
    rendered_body = None
    patient_information = patient_information_from_assignment(db, session)
    patient_name = None
    if db is not None and session.patient_id:
        patient = db.execute(
            select(Patient).where(Patient.id == session.patient_id, Patient.tenant_id == session.tenant_id)
        ).scalar_one_or_none()
        patient_name = patient.display_name if patient is not None else None
    if structured_report is not None:
        rendered_body = render_report_body_markdown(
            structured_report,
            db=db,
            session=session,
        )
        contracts["report"] = {
            **contracts["report"],
            "format": "markdown",
            "body": rendered_body,
            "sections": [{"id": "body", "title": "Body", "body": rendered_body}],
            "structuredModel": structured_report,
            "patientInformation": patient_information,
            "template": report_template_context(session.report_template_key),
            "patientInformationSource": patient_information["source"],
        }
    return {
        "id": str(session.id),
        "tenantId": str(session.tenant_id),
        "patientId": str(session.patient_id) if session.patient_id else None,
        "patientName": patient_name,
        "assignmentSource": assignment_source if isinstance(assignment_source, str) else None,
        # Author attribution + ownership (AES-901/902): deterministic, from created_by_user_id.
        # The owner is the creator; viewer-relative edit/reassign rights are resolved client-side
        # from the tenant's role permissions (and enforced server-side in the routes).
        "createdByUserId": str(session.created_by_user_id) if session.created_by_user_id else None,
        "ownerUserId": str(session.created_by_user_id) if session.created_by_user_id else None,
        "createdBy": attribution_payload(db, session.created_by_user_id),
        "status": session.status.value,
        "complete": session_is_complete(session),
        "title": session.title,
        "summary": session.summary,
        "generatedSummary": session.generated_summary,
        "generatedReport": rendered_body or session.generated_report,
        "reportModel": structured_report,
        "extractedMetadata": extracted_metadata,
        "reportTemplateKey": session.report_template_key,
        "organizationSource": session.organization_source.value,
        "createdAt": session.created_at.isoformat() if session.created_at else None,
        "updatedAt": session.updated_at.isoformat() if session.updated_at else None,
        "capturedAt": session.captured_at.isoformat() if session.captured_at else None,
        **contracts,
    }


def list_sessions_for_tenant(db: DbSession, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
    sessions = db.execute(
        select(Session).where(Session.tenant_id == tenant_id).order_by(Session.updated_at.desc())
    ).scalars()
    return [session_payload(session, db) for session in sessions]


def capture_payload(capture: Capture, artifact: Artifact | None = None, db: DbSession | None = None) -> dict[str, Any]:
    from app.services.attribution import attribution_payload

    metadata = capture.capture_metadata or {}
    return {
        "id": str(capture.id),
        "tenantId": str(capture.tenant_id),
        "sessionId": str(capture.session_id),
        "patientId": str(capture.patient_id) if capture.patient_id else None,
        "type": capture.capture_type.value,
        "status": capture.status.value,
        "title": metadata.get("title"),
        "clientCaptureId": capture.client_capture_id,
        "metadata": metadata,
        "assignmentSource": metadata.get("patient_assignment_source"),
        # Author attribution (AES-901): who captured this, from created_by_user_id (deterministic).
        # `createdBy.displayName` is None when `db` isn't passed; `createdByUserId` is always present.
        "createdByUserId": str(capture.created_by_user_id) if capture.created_by_user_id else None,
        "createdBy": attribution_payload(db, capture.created_by_user_id),
        "sourceArtifactId": str(capture.source_artifact_id) if capture.source_artifact_id else None,
        "artifact": artifact_payload(artifact) if artifact else None,
        "fileEndpoint": f"/api/v1/captures/{capture.id}/file" if capture.source_artifact_id else None,
        "capturedAt": capture.captured_at.isoformat() if capture.captured_at else None,
    }


def artifact_payload(artifact: Artifact) -> dict[str, Any]:
    return {
        "id": str(artifact.id),
        "kind": artifact.artifact_kind.value,
        "mimeType": artifact.mime_type,
        "byteSize": artifact.byte_size,
        "checksumSha256": artifact.checksum_sha256,
        "generatedBy": artifact.generated_by,
        "createdAt": artifact.created_at.isoformat() if artifact.created_at else None,
    }


def ensure_session(
    db: DbSession,
    *,
    principal: CurrentPrincipal,
    session_id: str | None,
    capture_type: CaptureType,
    captured_at: datetime,
) -> Session:
    if session_id:
        try:
            session = get_session_for_tenant(db, principal.tenant_id, uuid.UUID(session_id))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session_id") from exc
        return session

    session = Session(
        tenant_id=principal.tenant_id,
        patient_id=None,
        status=SessionStatus.draft,
        title=f"Session {captured_at.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        summary="Ready for progressive capture.",
        organization_source=OrganizationSource.none,
        created_by_user_id=principal.user_id,
        captured_at=captured_at,
    )
    db.add(session)
    db.flush()
    return session


async def upload_source_capture(
    db: DbSession,
    *,
    object_store: ObjectStore,
    principal: CurrentPrincipal,
    capture_type_text: str,
    session_id: str | None,
    patient_id: str | None,
    client_capture_id: str,
    detail: str,
    file: UploadFile,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        capture_type = CaptureType(capture_type_text)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported capture type") from exc

    content = await file.read()
    existing = db.execute(
        select(Capture).where(
            Capture.tenant_id == principal.tenant_id,
            Capture.created_by_user_id == principal.user_id,
            Capture.client_capture_id == client_capture_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        artifact = db.get(Artifact, existing.source_artifact_id) if existing.source_artifact_id else None
        if artifact is None or artifact.byte_size == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Existing capture file is empty. Retake photo")
        session = get_session_for_tenant(db, principal.tenant_id, existing.session_id)
        return {"session": session_payload(session, db), "item": capture_payload(existing, artifact, db)}

    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Capture file is empty")
    if capture_type == CaptureType.audio:
        validate_wav_pcm_16k_mono(content)
    if capture_type == CaptureType.note:
        detail = note_detail_with_file_fallback(detail, content)
    byte_size = len(content)
    checksum = hashlib.sha256(content).hexdigest()
    content_type = "audio/wav" if capture_type == CaptureType.audio else file.content_type or "application/octet-stream"
    captured_at = utc_now()
    object_key: str | None = None

    try:
        patient_uuid = uuid.UUID(patient_id) if patient_id else None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid patient_id") from exc
    if patient_uuid is not None:
        patient_exists = db.execute(
            select(Patient.id).where(Patient.id == patient_uuid, Patient.tenant_id == principal.tenant_id)
        ).scalar_one_or_none()
        if patient_exists is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    try:
        session = ensure_session(
            db,
            principal=principal,
            session_id=session_id,
            capture_type=capture_type,
            captured_at=captured_at,
        )
        capture = Capture(
            tenant_id=principal.tenant_id,
            session_id=session.id,
            patient_id=patient_uuid or session.patient_id,
            capture_type=capture_type,
            status=CaptureStatus.processing,
            client_capture_id=client_capture_id,
            capture_metadata={
                "detail": detail,
                "original_filename": file.filename,
                "content_type": content_type,
                **(metadata or {}),
            },
            captured_at=captured_at,
            created_by_user_id=principal.user_id,
        )
        db.add(capture)
        db.flush()

        artifact = Artifact(
            tenant_id=principal.tenant_id,
            capture_id=capture.id,
            session_id=session.id,
            artifact_kind=ArtifactKind.source,
            bucket=object_store.bucket,
            object_key="pending",
            mime_type=content_type,
            byte_size=byte_size,
            checksum_sha256=checksum,
            created_by_user_id=principal.user_id,
        )
        db.add(artifact)
        db.flush()

        object_key = object_key_for_source(principal.tenant_id, session.id, capture.id, artifact.id)
        object_store.put_object(
            object_key=object_key,
            data=io.BytesIO(content),
            length=byte_size,
            content_type=content_type,
            metadata={
                "tenant-id": str(principal.tenant_id),
                "session-id": str(session.id),
                "capture-id": str(capture.id),
                "artifact-id": str(artifact.id),
                "checksum-sha256": checksum,
            },
        )

        artifact.object_key = object_key
        capture.source_artifact_id = artifact.id
        from app.services.ai_jobs import create_capture_processing_job, dispatch_capture_processing_job
        from app.services.capabilities import tenant_processes_captures_with_ai

        # Zero-AI Basic lifecycle (AES-101): a capture with no capture-AI capabilities is saved
        # deterministically — no AI job, no `processing` state. Pro/therapy run the job as before.
        runs_capture_ai = tenant_processes_captures_with_ai(db, principal.tenant_id)
        ai_job = create_capture_processing_job(db, principal=principal, capture=capture) if runs_capture_ai else None
        if patient_uuid and session.patient_id is None:
            session.patient_id = patient_uuid
        evolve_session_after_capture(session, capture_type=capture_type, captured_at=captured_at, capture_id=capture.id)
        session.updated_at = utc_now()
        if runs_capture_ai:
            # A new capture changes the patient's memory — flag it refreshing (AI-job latency).
            mark_patient_memory_updating(db, session.patient_id)

        audit(
            db,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            action="capture.upload",
            target_type="capture",
            target_id=capture.id,
            details={"artifact_id": str(artifact.id), "byte_size": byte_size, "checksum_sha256": checksum},
        )
        db.commit()
        db.refresh(session)
        db.refresh(capture)
        db.refresh(artifact)
        if runs_capture_ai:
            db.refresh(ai_job)
            from app.services.ai_jobs import is_capture_chain_head

            # Same-session captures process in order; only dispatch when this is the chain head.
            if is_capture_chain_head(db, ai_job):
                dispatch_capture_processing_job(db, ai_job)
            db.refresh(ai_job)
        else:
            # Basic: no worker job will rebuild the report, so rebuild it synchronously (deterministic).
            from app.services.ai_jobs import regenerate_session_report_if_idle

            regenerate_session_report_if_idle(db, tenant_id=principal.tenant_id, session_id=session.id)
            db.refresh(session)
        from app.services.ai_jobs import ai_job_payload

        return {
            "session": session_payload(session, db),
            "item": capture_payload(capture, artifact, db),
            "processingJob": ai_job_payload(ai_job) if ai_job else None,
        }
    except Exception:
        # Product-critical: a failed capture upload breaks the capture-first promise. Count it for
        # the FailedUploadsSpike alert (engram_capture_uploads_failed_total).
        record_capture_upload_failed()
        db.rollback()
        if object_key is not None:
            try:
                object_store.delete_object(object_key)
            except Exception:
                pass
        raise


def source_file_url(db: DbSession, *, object_store: ObjectStore, principal: CurrentPrincipal, capture_id: str) -> dict[str, Any]:
    try:
        capture_uuid = uuid.UUID(capture_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid capture_id") from exc

    capture = db.execute(
        select(Capture).where(Capture.id == capture_uuid, Capture.tenant_id == principal.tenant_id)
    ).scalar_one_or_none()
    if capture is None or capture.source_artifact_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capture file not found")

    artifact = db.execute(
        select(Artifact).where(Artifact.id == capture.source_artifact_id, Artifact.tenant_id == principal.tenant_id)
    ).scalar_one_or_none()
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="artifact.preview",
        target_type="artifact",
        target_id=artifact.id,
        details={"capture_id": str(capture.id)},
    )
    db.commit()
    return {
        "url": object_store.presigned_get_url(artifact.object_key),
        "expiresInSeconds": settings.object_storage_presigned_url_ttl_seconds,
        "artifact": artifact_payload(artifact),
    }


def source_file_content(db: DbSession, *, object_store: ObjectStore, principal: CurrentPrincipal, capture_id: str) -> dict[str, Any]:
    try:
        capture_uuid = uuid.UUID(capture_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid capture_id") from exc

    capture = db.execute(
        select(Capture).where(Capture.id == capture_uuid, Capture.tenant_id == principal.tenant_id)
    ).scalar_one_or_none()
    if capture is None or capture.source_artifact_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capture file not found")

    artifact = db.execute(
        select(Artifact).where(Artifact.id == capture.source_artifact_id, Artifact.tenant_id == principal.tenant_id)
    ).scalar_one_or_none()
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="artifact.download",
        target_type="artifact",
        target_id=artifact.id,
        details={"capture_id": str(capture.id)},
    )
    db.commit()
    return {
        "content": object_store.get_object_bytes(artifact.object_key),
        "media_type": artifact.mime_type,
        "filename": (capture.capture_metadata or {}).get("original_filename") or f"{capture.id}",
    }


def internal_source_file_content(db: DbSession, *, object_store: ObjectStore, capture_id: str) -> dict[str, Any]:
    """Return source file bytes for trusted internal AI engine processors."""
    try:
        capture_uuid = uuid.UUID(capture_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid capture_id") from exc

    capture = db.execute(select(Capture).where(Capture.id == capture_uuid)).scalar_one_or_none()
    if capture is None or capture.source_artifact_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capture file not found")

    artifact = db.execute(
        select(Artifact).where(Artifact.id == capture.source_artifact_id, Artifact.tenant_id == capture.tenant_id)
    ).scalar_one_or_none()
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    return {
        "content": object_store.get_object_bytes(artifact.object_key),
        "media_type": artifact.mime_type,
        "filename": (capture.capture_metadata or {}).get("original_filename") or f"{capture.id}",
    }


def get_capture_for_tenant(db: DbSession, tenant_id: uuid.UUID, capture_id: uuid.UUID) -> Capture:
    capture = db.execute(
        select(Capture).where(Capture.id == capture_id, Capture.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if capture is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capture not found")
    return capture
