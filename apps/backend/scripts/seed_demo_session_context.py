"""Seed rich demo data for testing the session-context card + Q3 carry-forward (Pro tenant).

Run inside the backend container (it has DB + object storage + the app package):

    docker exec notari-main-backend-1 python /app/scripts/seed_demo_session_context.py

Idempotent by patient display name: a patient that already exists in the Pro demo tenant is
skipped (re-run safe). Creates real photo (PNG) + voice-memo (WAV) artifacts in MinIO, backdated
across visits, plus a prior-visit treatments[] for the carry-forward case. Zero AI jobs are
dispatched — this is pure prior-visit data for the deterministic context surface.
"""
from __future__ import annotations

import hashlib
import io
import math
import struct
import uuid
import zlib
from datetime import datetime, timedelta, timezone

from app.auth.service import DEV_NAMESPACE, DEV_TENANT_ID
from app.db.session import SessionLocal
from app.models import (
    AftercareTemplate,
    Artifact,
    ArtifactKind,
    Capture,
    CaptureStatus,
    CaptureType,
    OrganizationSource,
    Patient,
    PatientStatus,
    Session,
    SessionStatus,
)
from app.services.ai_jobs.orchestration import maybe_refresh_stale_patient_memory
from app.services.capture_storage import object_key_for_source
from app.storage.object_store import ObjectStore

DOCTOR_USER_ID = uuid.uuid5(DEV_NAMESPACE, "user:doctor")
NOW = datetime.now(timezone.utc)


def png_solid(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """A minimal solid-colour truecolour PNG (so before/after thumbs are visually distinct)."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit, colour type 2 (RGB)
    row = b"\x00" + bytes(rgb) * width  # filter byte 0 + pixels
    raw = row * height
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def wav_beep(seconds: float = 0.4, freq: int = 440, rate: int = 16000) -> bytes:
    """A short, valid 16 kHz mono 16-bit PCM WAV (audible so the digest's player is testable)."""
    n = int(seconds * rate)
    frames = b"".join(struct.pack("<h", int(2500 * math.sin(2 * math.pi * freq * i / rate))) for i in range(n))
    header = b"RIFF" + struct.pack("<I", 36 + len(frames)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    header += b"data" + struct.pack("<I", len(frames))
    return header + frames


def add_note(db, session: Session, *, detail: str, captured_at: datetime) -> Capture:
    capture = Capture(
        tenant_id=DEV_TENANT_ID,
        session_id=session.id,
        patient_id=session.patient_id,
        capture_type=CaptureType.note,
        status=CaptureStatus.received,
        client_capture_id=f"seed-{uuid.uuid4()}",
        capture_metadata={"detail": detail},
        captured_at=captured_at,
        created_by_user_id=DOCTOR_USER_ID,
    )
    db.add(capture)
    db.flush()
    return capture


def add_media(
    db,
    store: ObjectStore,
    session: Session,
    *,
    capture_type: CaptureType,
    content: bytes,
    content_type: str,
    filename: str,
    captured_at: datetime,
    caption: str | None = None,
) -> Capture:
    metadata: dict = {"detail": "", "original_filename": filename, "content_type": content_type}
    if caption:
        metadata["caption"] = {"text": caption, "source": "seed"}
    capture = Capture(
        tenant_id=DEV_TENANT_ID,
        session_id=session.id,
        patient_id=session.patient_id,
        capture_type=capture_type,
        status=CaptureStatus.received,
        client_capture_id=f"seed-{uuid.uuid4()}",
        capture_metadata=metadata,
        captured_at=captured_at,
        created_by_user_id=DOCTOR_USER_ID,
    )
    db.add(capture)
    db.flush()
    artifact = Artifact(
        tenant_id=DEV_TENANT_ID,
        capture_id=capture.id,
        session_id=session.id,
        artifact_kind=ArtifactKind.source,
        bucket=store.bucket,
        object_key="pending",
        mime_type=content_type,
        byte_size=len(content),
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        created_by_user_id=DOCTOR_USER_ID,
    )
    db.add(artifact)
    db.flush()
    object_key = object_key_for_source(DEV_TENANT_ID, session.id, capture.id, artifact.id)
    store.put_object(object_key=object_key, data=io.BytesIO(content), length=len(content), content_type=content_type)
    artifact.object_key = object_key
    capture.source_artifact_id = artifact.id
    db.flush()
    return capture


def make_session(db, *, patient: Patient, title: str, days_ago: int, extracted_metadata: dict | None = None) -> Session:
    captured_at = NOW - timedelta(days=days_ago)
    session = Session(
        tenant_id=DEV_TENANT_ID,
        patient_id=patient.id,
        status=SessionStatus.needs_review,
        title=title,
        summary="Seeded prior visit.",
        organization_source=OrganizationSource.none,
        created_by_user_id=DOCTOR_USER_ID,
        captured_at=captured_at,
        extracted_metadata=extracted_metadata or {},
    )
    db.add(session)
    db.flush()
    return session


def ensure_patient(db, *, display_name: str, first: str, last: str, phone: str, notes: str | None) -> Patient | None:
    """Create the patient, or return None if one with this name already exists (skip → idempotent)."""
    existing = db.query(Patient).filter(Patient.tenant_id == DEV_TENANT_ID, Patient.display_name == display_name).first()
    if existing is not None:
        return None
    patient = Patient(
        tenant_id=DEV_TENANT_ID,
        display_name=display_name,
        legal_first_name=first,
        legal_last_name=last,
        phone=phone,
        notes=notes,
        status=PatientStatus.active,
        created_by_user_id=DOCTOR_USER_ID,
    )
    db.add(patient)
    db.flush()
    return patient


def ensure_aftercare_template(db, *, name: str, procedure_type: str, body: str) -> bool:
    """Create a clinic aftercare template, or return False if one with this name already exists."""
    existing = (
        db.query(AftercareTemplate)
        .filter(AftercareTemplate.tenant_id == DEV_TENANT_ID, AftercareTemplate.name == name)
        .first()
    )
    if existing is not None:
        return False
    db.add(
        AftercareTemplate(
            tenant_id=DEV_TENANT_ID,
            name=name,
            procedure_type=procedure_type,
            body=body,
            is_active=True,
            created_by_user_id=DOCTOR_USER_ID,
        )
    )
    return True


def main() -> None:
    db = SessionLocal()
    store = ObjectStore()
    created: list[str] = []
    skipped: list[str] = []
    try:
        # Clinic aftercare templates (deterministic, Persian) — one-tap follow-up in the session.
        if ensure_aftercare_template(
            db, name="مراقبت بعد از بوتاکس", procedure_type="botox",
            body="تا ۴ ساعت دراز نکشید. ۲۴ ساعت ورزش سنگین و ماساژ ناحیه ممنوع. تا ۳ روز از سونا و آفتاب مستقیم پرهیز کنید.",
        ):
            created.append("aftercare template: مراقبت بعد از بوتاکس")
        else:
            skipped.append("aftercare template: مراقبت بعد از بوتاکس")
        if ensure_aftercare_template(
            db, name="مراقبت بعد از فیلر", procedure_type="filler",
            body="تا ۲۴ ساعت آرایش نکنید. کمپرس سرد برای کاهش تورم. تا ۲ هفته از حرارت زیاد (سونا/سولاریوم) پرهیز کنید.",
        ):
            created.append("aftercare template: مراقبت بعد از فیلر")
        else:
            skipped.append("aftercare template: مراقبت بعد از فیلر")

        # A — rich returning patient: 3 prior visits, key facts, the last visit a full digest.
        negar = ensure_patient(
            db, display_name="نگار محمدی", first="نگار", last="محمدی", phone="+98 912 100 1001",
            notes="آلرژی به لیدوکائین. ترجیح می‌دهد دوران نقاهت کوتاه باشد.",
        )
        if negar:
            v1 = make_session(db, patient=negar, title="جلسه اول", days_ago=90)
            add_note(db, v1, detail="اولین جلسه. بوتاکس پیشانی ۲۰ واحد.", captured_at=v1.captured_at)
            add_media(db, store, v1, capture_type=CaptureType.photo, content=png_solid(220, 220, (210, 180, 170)),
                      content_type="image/png", filename="v1-forehead.png", captured_at=v1.captured_at, caption="پیشانی، قبل")
            v2 = make_session(db, patient=negar, title="جلسه دوم", days_ago=45)
            add_note(db, v2, detail="فیلر گونه چپ یک سی‌سی.", captured_at=v2.captured_at)
            add_media(db, store, v2, capture_type=CaptureType.photo, content=png_solid(220, 220, (205, 175, 165)),
                      content_type="image/png", filename="v2-cheek.png", captured_at=v2.captured_at, caption="گونه چپ")
            v3 = make_session(db, patient=negar, title="جلسه سوم", days_ago=10)
            add_note(db, v3, detail="بررسی نتیجه. رضایت بیمار خوب بود. فیلر گونه راست نیم سی‌سی.", captured_at=v3.captured_at)
            add_media(db, store, v3, capture_type=CaptureType.photo, content=png_solid(220, 220, (200, 170, 160)),
                      content_type="image/png", filename="v3-right.png", captured_at=v3.captured_at, caption="گونه راست، بعد")
            add_media(db, store, v3, capture_type=CaptureType.photo, content=png_solid(220, 220, (195, 165, 155)),
                      content_type="image/png", filename="v3-front.png", captured_at=v3.captured_at, caption="نمای روبرو")
            add_media(db, store, v3, capture_type=CaptureType.audio, content=wav_beep(0.5, 520),
                      content_type="audio/wav", filename="v3-memo.wav", captured_at=v3.captured_at)
            created.append("نگار محمدی — 3 visits (digest + strip + key facts + voice memo)")
        else:
            skipped.append("نگار محمدی")

        # B — single prior visit: digest only, no progress strip.
        sara = ensure_patient(db, display_name="سارا احمدی", first="سارا", last="احمدی", phone="+98 912 200 2002", notes=None)
        if sara:
            b1 = make_session(db, patient=sara, title="جلسه اول", days_ago=20)
            add_note(db, b1, detail="مشاوره و بوتاکس اخم ۱۵ واحد.", captured_at=b1.captured_at)
            add_media(db, store, b1, capture_type=CaptureType.photo, content=png_solid(220, 220, (180, 195, 205)),
                      content_type="image/png", filename="b1-glabella.png", captured_at=b1.captured_at, caption="اخم")
            created.append("سارا احمدی — 1 visit (digest only, no strip)")
        else:
            skipped.append("سارا احمدی")

        # C — carry-forward (Q3): a prior visit with a stored treatment to carry "same as last time".
        maryam = ensure_patient(db, display_name="مریم رضایی", first="مریم", last="رضایی", phone="+98 912 300 3003", notes=None)
        if maryam:
            c1 = make_session(db, patient=maryam, title="جلسه اول", days_ago=30)
            note = add_note(db, c1, detail="بوتاکس پیشانی ۲۰ واحد.", captured_at=c1.captured_at)
            c1.extracted_metadata = {
                "treatments": [
                    {
                        "area": "پیشانی",
                        "product": "بوتاکس",
                        "brand": None,
                        "quantity": 20,
                        "unit": "unit",
                        "quantityText": "۲۰ واحد",
                        "lot": None,
                        "confidence": 0.92,
                        "carriedForward": False,
                        "sourceCaptureIds": [str(note.id)],
                    }
                ]
            }
            db.flush()
            created.append("مریم رضایی — prior Botox 20u (start a NEW visit + dictate 'مثل دفعه قبل' → carry-forward)")
        else:
            skipped.append("مریم رضایی")

        # D — brand-new patient with only a pinned key fact (key-facts-only card path).
        leila = ensure_patient(
            db, display_name="لیلا کریمی", first="لیلا", last="کریمی", phone="+98 912 400 4004",
            notes="حساسیت پوستی به محصولات حاوی الکل.",
        )
        if leila:
            created.append("لیلا کریمی — new patient, key-facts only (no prior visit)")
        else:
            skipped.append("لیلا کریمی")

        db.commit()

        # Pre-warm Pro patient memory (Job 4) so demo patients aren't "organizing" on first open —
        # dispatch the same read-trigger a real open would; the worker generates it in the background.
        # Re-queries by name (not just newly-created) so a re-run also warms any still-cold patient.
        for name in ("نگار محمدی", "سارا احمدی", "مریم رضایی"):
            patient = db.query(Patient).filter(Patient.tenant_id == DEV_TENANT_ID, Patient.display_name == name).first()
            if patient is None:
                continue
            patient_sessions = list(
                db.query(Session).filter(Session.tenant_id == DEV_TENANT_ID, Session.patient_id == patient.id).all()
            )
            if maybe_refresh_stale_patient_memory(
                db,
                tenant_id=DEV_TENANT_ID,
                patient=patient,
                sessions=patient_sessions,
                created_by_user_id=DOCTOR_USER_ID,
            ):
                created.append(f"pre-warmed memory: {name}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print("Seed complete (Pro tenant: Memara Demo Clinic).")
    for line in created:
        print("  + created:", line)
    for name in skipped:
        print("  · skipped (already exists):", name)
    if not created:
        print("  (nothing new — all demo patients already present)")


if __name__ == "__main__":
    main()
