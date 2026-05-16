import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.auth.service import audit
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
    Session,
    SessionStatus,
)
from app.services.capture_storage import (
    artifact_payload,
    capture_payload,
    create_generated_artifact,
    get_capture_for_tenant,
    get_session_for_tenant,
    session_payload,
)
from app.services.sessions import parse_uuid
from app.storage import ObjectStore


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generated_marker(job: FakeJob) -> dict[str, str]:
    return {
        "generated_by": "fake-processing",
        "fake_job_id": str(job.id),
        "generated_at": utc_now().isoformat(),
    }


def fake_job_payload(job: FakeJob) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "tenantId": str(job.tenant_id),
        "sessionId": str(job.session_id) if job.session_id else None,
        "captureId": str(job.capture_id) if job.capture_id else None,
        "jobType": job.job_type.value,
        "status": job.status.value,
        "generatedBy": job.generated_by,
        "inputArtifactIds": job.input_artifact_ids,
        "resultMetadata": job.result_metadata,
        "errorMessage": job.error_message,
        "createdByUserId": str(job.created_by_user_id) if job.created_by_user_id else None,
        "createdAt": job.created_at.isoformat() if job.created_at else None,
        "startedAt": job.started_at.isoformat() if job.started_at else None,
        "completedAt": job.completed_at.isoformat() if job.completed_at else None,
    }


def get_fake_job(db: DbSession, principal: CurrentPrincipal, job_id: str) -> dict[str, Any]:
    job = db.execute(
        select(FakeJob).where(
            FakeJob.id == parse_uuid(job_id, "job_id"),
            FakeJob.tenant_id == principal.tenant_id,
        )
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fake job not found")
    return fake_job_payload(job)


def create_job(
    db: DbSession,
    *,
    principal: CurrentPrincipal,
    job_type: FakeJobType,
    session_id: uuid.UUID | None,
    capture_id: uuid.UUID | None = None,
    input_artifact_ids: list[str] | None = None,
) -> FakeJob:
    job = FakeJob(
        tenant_id=principal.tenant_id,
        session_id=session_id,
        capture_id=capture_id,
        job_type=job_type,
        status=FakeJobStatus.running,
        generated_by="fake-processing",
        input_artifact_ids=input_artifact_ids or [],
        result_metadata={},
        created_by_user_id=principal.user_id,
        started_at=utc_now(),
    )
    db.add(job)
    db.flush()
    return job


def fake_text_for_capture(capture: Capture) -> str:
    detail = (capture.capture_metadata or {}).get("detail") or "No clinician detail was provided."
    if capture.capture_type == CaptureType.audio:
        return (
            "Fake transcript: clinician discusses aesthetic goals, prior treatment tolerance, "
            f"and follow-up plan. Source note: {detail}"
        )
    if capture.capture_type == CaptureType.photo:
        return (
            "Fake OCR/description: treatment-area photo with visible clinic annotation and "
            f"placeholder findings. Source note: {detail}"
        )
    return f"Fake normalized note: {str(detail).strip() or 'Captured note reviewed.'}"


def artifact_kind_for_capture(capture: Capture) -> ArtifactKind:
    if capture.capture_type == CaptureType.audio:
        return ArtifactKind.transcript
    if capture.capture_type == CaptureType.photo:
        return ArtifactKind.ocr_text
    return ArtifactKind.normalized_note


def metadata_key_for_capture(capture: Capture) -> str:
    if capture.capture_type == CaptureType.audio:
        return "transcript"
    if capture.capture_type == CaptureType.photo:
        return "ocr"
    return "normalized_note"


def process_capture_inline(
    db: DbSession,
    *,
    object_store: ObjectStore,
    principal: CurrentPrincipal,
    capture: Capture,
) -> tuple[FakeJob, Artifact]:
    source_ids = [str(capture.source_artifact_id)] if capture.source_artifact_id else []
    job = create_job(
        db,
        principal=principal,
        job_type=FakeJobType.capture_process,
        session_id=capture.session_id,
        capture_id=capture.id,
        input_artifact_ids=source_ids,
    )
    capture.status = CaptureStatus.processing

    output_text = fake_text_for_capture(capture)
    artifact = create_generated_artifact(
        db,
        object_store=object_store,
        principal=principal,
        session_id=str(capture.session_id),
        content=output_text.encode("utf-8"),
        artifact_kind=artifact_kind_for_capture(capture),
        mime_type="text/plain; charset=utf-8",
        generated_by="fake-processing",
        fake_job=job,
        capture_id=capture.id,
    )

    marker = generated_marker(job)
    key = metadata_key_for_capture(capture)
    type_payload: dict[str, Any] = {
        **marker,
        "status": "completed",
        "text": output_text,
        "artifact_id": str(artifact.id),
        "source_artifact_ids": source_ids,
    }
    if capture.capture_type == CaptureType.audio:
        type_payload["language"] = (capture.capture_metadata or {}).get("language", "en")
        type_payload["duration"] = (capture.capture_metadata or {}).get("duration")
        type_payload["codec"] = (capture.capture_metadata or {}).get("codec")
    elif capture.capture_type == CaptureType.photo:
        type_payload["width"] = (capture.capture_metadata or {}).get("width")
        type_payload["height"] = (capture.capture_metadata or {}).get("height")
    else:
        type_payload["language"] = (capture.capture_metadata or {}).get("language", "en")

    capture.capture_metadata = {**(capture.capture_metadata or {}), key: type_payload}
    capture.status = CaptureStatus.processed
    job.status = FakeJobStatus.succeeded
    job.completed_at = utc_now()
    job.result_metadata = {
        "artifact_id": str(artifact.id),
        "artifact_kind": artifact.artifact_kind.value,
        key: type_payload,
    }
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="fake_processing.complete",
        target_type="capture",
        target_id=capture.id,
        details={"fake_job_id": str(job.id), "artifact_id": str(artifact.id)},
    )
    return job, artifact


def fake_process_capture(
    db: DbSession,
    *,
    object_store: ObjectStore,
    principal: CurrentPrincipal,
    capture_id: str,
) -> dict[str, Any]:
    artifact: Artifact | None = None
    try:
        capture = get_capture_for_tenant(db, principal.tenant_id, parse_uuid(capture_id, "capture_id"))
        job, artifact = process_capture_inline(db, object_store=object_store, principal=principal, capture=capture)
        db.commit()
        db.refresh(capture)
        db.refresh(job)
        db.refresh(artifact)
        return {"fakeJob": fake_job_payload(job), "capture": capture_payload(capture), "artifact": artifact_payload(artifact)}
    except Exception:
        db.rollback()
        if artifact is not None and artifact.object_key != "pending":
            try:
                object_store.delete_object(artifact.object_key)
            except Exception:
                pass
        raise


def summary_from_captures(captures: list[Capture]) -> str:
    if not captures:
        return "Fake summary: no captures were available, but the session is organized for review."
    fragments: list[str] = []
    for capture in captures[:4]:
        metadata = capture.capture_metadata or {}
        detail = metadata.get("detail")
        generated = metadata.get("transcript") or metadata.get("ocr") or metadata.get("normalized_note") or {}
        text = generated.get("text") or detail or capture.capture_type.value
        fragments.append(str(text)[:180])
    return "Fake session summary: " + " ".join(fragments)


def fake_organize_session(
    db: DbSession,
    *,
    object_store: ObjectStore,
    principal: CurrentPrincipal,
    session_id: str,
) -> dict[str, Any]:
    summary_artifact: Artifact | None = None
    generated_artifacts: list[Artifact] = []
    try:
        session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
        session.status = SessionStatus.processing
        captures = list(
            db.execute(
                select(Capture)
                .where(Capture.tenant_id == principal.tenant_id, Capture.session_id == session.id)
                .order_by(Capture.created_at)
            ).scalars()
        )
        processed_jobs: list[FakeJob] = []
        for capture in captures:
            if capture.status != CaptureStatus.processed:
                job, artifact = process_capture_inline(db, object_store=object_store, principal=principal, capture=capture)
                processed_jobs.append(job)
                generated_artifacts.append(artifact)

        org_job = create_job(
            db,
            principal=principal,
            job_type=FakeJobType.session_organize,
            session_id=session.id,
            input_artifact_ids=[str(capture.source_artifact_id) for capture in captures if capture.source_artifact_id],
        )
        summary = summary_from_captures(captures)
        summary_artifact = create_generated_artifact(
            db,
            object_store=object_store,
            principal=principal,
            session_id=str(session.id),
            content=summary.encode("utf-8"),
            artifact_kind=ArtifactKind.summary,
            mime_type="text/plain; charset=utf-8",
            generated_by="fake-processing",
            fake_job=org_job,
        )
        org_job.status = FakeJobStatus.succeeded
        org_job.completed_at = utc_now()
        org_job.result_metadata = {
            "summary": {
                **generated_marker(org_job),
                "text": summary,
                "artifact_id": str(summary_artifact.id),
                "source_capture_ids": [str(capture.id) for capture in captures],
                "source_artifact_ids": [str(capture.source_artifact_id) for capture in captures if capture.source_artifact_id],
            },
            "processed_capture_job_ids": [str(job.id) for job in processed_jobs],
        }
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
            details={"fake_job_id": str(org_job.id), "artifact_id": str(summary_artifact.id)},
        )
        db.commit()
        db.refresh(session)
        db.refresh(org_job)
        db.refresh(summary_artifact)
        return {
            "fakeJob": fake_job_payload(org_job),
            "session": session_payload(session),
            "artifact": artifact_payload(summary_artifact),
        }
    except Exception:
        db.rollback()
        for artifact in [*generated_artifacts, summary_artifact]:
            if artifact is not None and artifact.object_key != "pending":
                try:
                    object_store.delete_object(artifact.object_key)
                except Exception:
                    pass
        raise
