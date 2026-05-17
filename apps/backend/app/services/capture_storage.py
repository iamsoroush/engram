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
    FakeJob,
    FakeJobStatus,
    FakeJobType,
    OrganizationSource,
    Patient,
    Session,
    SessionStatus,
)
from app.storage import ObjectStore


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def object_key_for_source(tenant_id: uuid.UUID, session_id: uuid.UUID, capture_id: uuid.UUID, artifact_id: uuid.UUID) -> str:
    return f"tenants/{tenant_id}/sessions/{session_id}/captures/{capture_id}/source/{artifact_id}"


def object_key_for_generated(
    tenant_id: uuid.UUID,
    session_id: uuid.UUID,
    artifact_id: uuid.UUID,
    capture_id: uuid.UUID | None = None,
) -> str:
    if capture_id:
        return f"tenants/{tenant_id}/sessions/{session_id}/captures/{capture_id}/generated/{artifact_id}"
    return f"tenants/{tenant_id}/sessions/{session_id}/generated/{artifact_id}"


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


def get_session_for_tenant(db: DbSession, tenant_id: uuid.UUID, session_id: uuid.UUID) -> Session:
    session = db.execute(
        select(Session).where(Session.id == session_id, Session.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


def session_payload(session: Session) -> dict[str, Any]:
    return {
        "id": str(session.id),
        "tenantId": str(session.tenant_id),
        "patientId": str(session.patient_id) if session.patient_id else None,
        "status": session.status.value,
        "title": session.title,
        "summary": session.summary,
        "generatedSummary": session.generated_summary,
        "organizationSource": session.organization_source.value,
        "createdAt": session.created_at.isoformat() if session.created_at else None,
        "updatedAt": session.updated_at.isoformat() if session.updated_at else None,
        "capturedAt": session.captured_at.isoformat() if session.captured_at else None,
    }


def list_sessions_for_tenant(db: DbSession, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
    sessions = db.execute(
        select(Session).where(Session.tenant_id == tenant_id).order_by(Session.updated_at.desc())
    ).scalars()
    return [session_payload(session) for session in sessions]


def capture_payload(capture: Capture, artifact: Artifact | None = None) -> dict[str, Any]:
    return {
        "id": str(capture.id),
        "tenantId": str(capture.tenant_id),
        "sessionId": str(capture.session_id),
        "patientId": str(capture.patient_id) if capture.patient_id else None,
        "type": capture.capture_type.value,
        "status": capture.status.value,
        "clientCaptureId": capture.client_capture_id,
        "metadata": capture.capture_metadata,
        "assignmentSource": (capture.capture_metadata or {}).get("patient_assignment_source"),
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
            return get_session_for_tenant(db, principal.tenant_id, uuid.UUID(session_id))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session_id") from exc

    session = Session(
        tenant_id=principal.tenant_id,
        patient_id=None,
        status=SessionStatus.unassigned,
        title=f"Session {captured_at.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        summary="Captured successfully. Ready to organize when there is time.",
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

    existing = db.execute(
        select(Capture).where(
            Capture.tenant_id == principal.tenant_id,
            Capture.created_by_user_id == principal.user_id,
            Capture.client_capture_id == client_capture_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        artifact = db.get(Artifact, existing.source_artifact_id) if existing.source_artifact_id else None
        session = get_session_for_tenant(db, principal.tenant_id, existing.session_id)
        return {"session": session_payload(session), "item": capture_payload(existing, artifact)}

    content = await file.read()
    if capture_type == CaptureType.audio:
        validate_wav_pcm_16k_mono(content)
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

        ai_job = create_capture_processing_job(db, principal=principal, capture=capture)
        if patient_uuid and session.patient_id is None:
            session.patient_id = patient_uuid
        session.updated_at = utc_now()
        if session.patient_id:
            session.status = SessionStatus.needs_review

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
        db.refresh(ai_job)
        dispatch_capture_processing_job(db, ai_job)
        db.refresh(ai_job)
        from app.services.ai_jobs import ai_job_payload

        return {"session": session_payload(session), "item": capture_payload(capture, artifact), "processingJob": ai_job_payload(ai_job)}
    except Exception:
        db.rollback()
        if object_key is not None:
            try:
                object_store.delete_object(object_key)
            except Exception:
                pass
        raise


def create_generated_artifact(
    db: DbSession,
    *,
    object_store: ObjectStore,
    principal: CurrentPrincipal,
    session_id: str,
    content: bytes,
    artifact_kind: ArtifactKind,
    mime_type: str,
    generated_by: str,
    fake_job: FakeJob | None = None,
    capture_id: uuid.UUID | None = None,
) -> Artifact:
    try:
        session = get_session_for_tenant(db, principal.tenant_id, uuid.UUID(session_id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session_id") from exc

    checksum = hashlib.sha256(content).hexdigest()
    object_key: str | None = None
    try:
        artifact = Artifact(
            tenant_id=principal.tenant_id,
            capture_id=capture_id,
            session_id=session.id,
            fake_job_id=fake_job.id if fake_job else None,
            artifact_kind=artifact_kind,
            bucket=object_store.bucket,
            object_key="pending",
            mime_type=mime_type,
            byte_size=len(content),
            checksum_sha256=checksum,
            generated_by=generated_by,
            created_by_user_id=principal.user_id,
        )
        db.add(artifact)
        db.flush()
        object_key = object_key_for_generated(principal.tenant_id, session.id, artifact.id, capture_id)
        object_store.put_object(
            object_key=object_key,
            data=io.BytesIO(content),
            length=len(content),
            content_type=mime_type,
            metadata={
                "tenant-id": str(principal.tenant_id),
                "session-id": str(session.id),
                "artifact-id": str(artifact.id),
                "checksum-sha256": checksum,
                "generated-by": generated_by,
            },
        )
        artifact.object_key = object_key
        return artifact
    except Exception:
        if object_key is not None:
            try:
                object_store.delete_object(object_key)
            except Exception:
                pass
        raise


def fake_organize_session(
    db: DbSession,
    *,
    object_store: ObjectStore,
    principal: CurrentPrincipal,
    session_id: str,
) -> dict[str, Any]:
    try:
        session = get_session_for_tenant(db, principal.tenant_id, uuid.UUID(session_id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session_id") from exc

    artifact: Artifact | None = None
    try:
        job = FakeJob(
            tenant_id=principal.tenant_id,
            session_id=session.id,
            job_type=FakeJobType.session_organize,
            status=FakeJobStatus.running,
            generated_by="fake-processing",
            input_artifact_ids=[],
            result_metadata={},
            created_by_user_id=principal.user_id,
            started_at=utc_now(),
        )
        db.add(job)
        db.flush()

        summary = "Reviewed and organized into the clinical record."
        artifact = create_generated_artifact(
            db,
            object_store=object_store,
            principal=principal,
            session_id=str(session.id),
            content=summary.encode("utf-8"),
            artifact_kind=ArtifactKind.summary,
            mime_type="text/plain; charset=utf-8",
            generated_by="fake-processing",
            fake_job=job,
        )
        job.status = FakeJobStatus.completed
        job.completed_at = utc_now()
        job.result_metadata = {"summary_artifact_id": str(artifact.id)}
        session.status = SessionStatus.organized
        session.generated_summary = summary
        session.organization_source = OrganizationSource.fake_processing
        session.updated_at = utc_now()
        audit(
            db,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            action="fake_processing.complete",
            target_type="session",
            target_id=session.id,
            details={"fake_job_id": str(job.id), "artifact_id": str(artifact.id)},
        )
        db.commit()
        db.refresh(session)
        db.refresh(artifact)
        return {"session": session_payload(session), "artifact": artifact_payload(artifact), "fakeJobId": str(job.id)}
    except Exception:
        db.rollback()
        if artifact is not None and artifact.object_key != "pending":
            try:
                object_store.delete_object(artifact.object_key)
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


def get_capture_for_tenant(db: DbSession, tenant_id: uuid.UUID, capture_id: uuid.UUID) -> Capture:
    capture = db.execute(
        select(Capture).where(Capture.id == capture_id, Capture.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if capture is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capture not found")
    return capture
