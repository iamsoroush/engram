"""Seed a rich, realistic dataset for testing the **Insights** analytics panel — with REAL AI.

Run inside the backend container (has DB + app package; the ai-engine worker + gateway do the AI):

    docker exec <branch>-backend-1 env PYTHONPATH=/app python /app/scripts/seed_insights_demo.py

What it creates in the Pro aesthetics demo tenant (``Engram Demo Clinic``):

- ~22 patients with varied **demographics** (age bands via ``date_of_birth``, sex, phone), each
  ``created_at`` backdated to their first visit — so age/sex/recency/growth + the New-patients KPI fill
  across ranges.
- ~50 **visits**: real Persian **text-note captures**, backdated across ~8 months at varied
  weekday/hour, attributed across **Dr. Demo** (doctor) and **Ari Assistant** (assistant).
- Every visit's note is processed by the **REAL AI pipeline** (``text_capture_process`` →
  ``session_organize`` synthesis on ``gpt-5.4-nano`` via the gateway) which extracts
  ``extracted_metadata["treatments"]`` from the note text — genuine AI, no MinIO (notes are passthrough).
- **Returning** patients (2–4 visits) + single-visit new patients, last-visit spread across
  active/lapsing/lapsed. A couple of "مثل دفعه قبل" notes exercise carry-forward.
- **Needs-attention** edge cases: unassigned captures, a few left in needs-review, one failed.

Finalized visits are set to ``verified`` after synthesis so they don't inflate the needs-review tile.
Idempotent by patient display name (re-run safe). Requires ``BACKEND_REPORT_SYNTHESIS_ENABLED=true``
and a reachable synthesis gateway (else treatments stay empty and it reports how many extracted).
"""
from __future__ import annotations

import random
import time
import uuid
from datetime import datetime, timedelta, timezone

from app.auth.service import DEV_NAMESPACE, DEV_TENANT_ID
from app.auth.dependencies import CurrentPrincipal
from app.db.session import SessionLocal
from app.models import (
    Capture, CaptureStatus, CaptureType, OrganizationSource, Patient, PatientStatus, Session, SessionStatus, Tenant, User,
)
from app.services.ai_jobs.orchestration import enqueue_capture_processing_job, maybe_refresh_stale_patient_memory

DOCTOR_ID = uuid.uuid5(DEV_NAMESPACE, "user:doctor")
ASSISTANT_ID = uuid.uuid5(DEV_NAMESPACE, "user:assistant")
NOW = datetime.now(timezone.utc)
RNG = random.Random(20260702)

# Persian clinical note templates — the real synthesis extracts treatments FROM this text.
NOTES = [
    "بوتاکس پیشانی ۲۰ واحد.",
    "بوتاکس پیشانی ۲۵ واحد و اخم ۱۵ واحد.",
    "بوتاکس دور چشم ۱۲ واحد با دیسپورت.",
    "بوتاکس اخم ۱۸ واحد.",
    "فیلر لب یک سی‌سی با ژوویدرم، لات JV-9910.",
    "فیلر لب نیم سی‌سی رستیلن.",
    "فیلر گونه دو سی‌سی، لات D-4471.",
    "فیلر گونه یک سی‌سی با تئوسیال.",
    "فیلر خط خنده یک سی‌سی.",
    "اسکین بوستر صورت دو سی‌سی پروفایلو.",
    "مزوتراپی صورت با ژلودرم یک سی‌سی.",
    "بوتاکس پیشانی ۲۰ واحد و فیلر لب نیم سی‌سی.",
    "فیلر گونه ۱.۵ سی‌سی رستیلن، لات RS-3321.",
]
CARRY_NOTE = "بوتاکس پیشانی مثل دفعه قبل."

FIRST_F = ["الهام", "پریسا", "شیرین", "مینا", "رها", "آیدا", "نیلوفر", "ترانه", "بهاره", "فرشته",
           "سمیرا", "غزل", "یاسمن", "هستی", "نازنین", "رویا", "مهسا", "کیمیا", "پرنیان", "آناهیتا"]
FIRST_M = ["کاوه", "بابک", "سامان", "آرش", "امیر", "پویا"]
LAST = ["تهرانی", "اکبری", "نوری", "صادقی", "حسینی", "جعفری", "رحیمی", "عباسی", "مرادی", "کاظمی",
        "یزدانی", "شریفی", "بهرامی", "فراهانی", "قاسمی", "زمانی", "سلطانی", "میرزایی", "خسروی", "نجفی"]

PLANS = {
    "active_returning": [230, 150, 70, 14],
    "active_pair": [95, 24],
    "active_new": [6],
    "recent_new": [2],
    "lapsing_pair": [175, 110],
    "lapsed": [265, 225],
    "mid_triple": [140, 80, 28],
}
PLAN_ASSIGNMENT = (["active_returning"] * 4 + ["active_pair"] * 4 + ["mid_triple"] * 3 + ["active_new"] * 3
                   + ["recent_new"] * 3 + ["lapsing_pair"] * 3 + ["lapsed"] * 2 + ["none", "none"])
AGE_BANDS = (["26-35"] * 9 + ["36-45"] * 6 + ["18-25"] * 4 + ["46-55"] * 3 + ["56+"] * 2)


def age_dob(band):
    lo, hi = {"18-25": (19, 25), "26-35": (26, 35), "36-45": (36, 45), "46-55": (46, 55), "56+": (56, 68)}[band]
    return NOW - timedelta(days=RNG.randint(lo, hi) * 365 + RNG.randint(0, 364))


def clinic_dt(days_ago):
    return (NOW - timedelta(days=days_ago)).replace(hour=RNG.randint(9, 19), minute=RNG.choice([0, 15, 30, 45]), second=0, microsecond=0)


def principal_for(db, user_id, role):
    return CurrentPrincipal(user=db.get(User, user_id), tenant=db.get(Tenant, DEV_TENANT_ID), roles=frozenset({role}), token_jti="seed")


def make_patient(db, first, last, dob, sex, phone, created_at):
    display = f"{first} {last}"
    if db.query(Patient).filter(Patient.tenant_id == DEV_TENANT_ID, Patient.display_name == display).first():
        return None
    p = Patient(tenant_id=DEV_TENANT_ID, display_name=display, legal_first_name=first, legal_last_name=last,
                date_of_birth=dob.date() if dob else None, sex=sex, phone=phone, status=PatientStatus.active,
                created_by_user_id=DOCTOR_ID, created_at=created_at)
    db.add(p); db.flush()
    return p


def make_visit(db, patient, days_ago, creator, role, note_text):
    when = clinic_dt(days_ago)
    s = Session(tenant_id=DEV_TENANT_ID, patient_id=patient.id, status=SessionStatus.draft, title="ویزیت",
                organization_source=OrganizationSource.none, created_by_user_id=creator, captured_at=when, created_at=when)
    db.add(s); db.flush()
    c = Capture(tenant_id=DEV_TENANT_ID, session_id=s.id, patient_id=patient.id, capture_type=CaptureType.note,
                status=CaptureStatus.processing, client_capture_id=f"ins-{uuid.uuid4()}",
                capture_metadata={"detail": note_text}, captured_at=when, created_at=when, created_by_user_id=creator)
    db.add(c); db.flush()
    enqueue_capture_processing_job(db, principal=principal_for(db, creator, role), capture_id=str(c.id))
    db.commit()
    return s.id, when


def main():
    db = SessionLocal()
    real_visit_ids: list[uuid.UUID] = []
    needs_review_ids: list[uuid.UUID] = []
    seeded_patients: list[uuid.UUID] = []
    created = skipped = 0
    try:
        plans = list(PLAN_ASSIGNMENT)
        for i in range(len(plans)):
            sex = "M" if RNG.random() < 0.18 else "F"
            first = RNG.choice(FIRST_M if sex == "M" else FIRST_F)
            last = LAST[i % len(LAST)]
            missing = RNG.random() < 0.1
            dob = None if missing else age_dob(AGE_BANDS[i % len(AGE_BANDS)])
            sex_val = None if missing else sex
            phone = f"+98 912 {RNG.randint(100, 999)} {RNG.randint(1000, 9999)}"
            days = PLANS.get(plans[i], [])
            created_at = NOW - timedelta(days=(max(days) if days else RNG.randint(20, 300)))
            patient = None
            base = first
            for attempt in range(5):
                patient = make_patient(db, first, last, dob, sex_val, phone, created_at)
                if patient:
                    break
                first = f"{base} {chr(ord('آ') + attempt + 1)}"
            if not patient:
                skipped += 1
                continue
            db.commit()
            created += 1
            seeded_patients.append(patient.id)
            for vi, days_ago in enumerate(days):
                creator, role = (ASSISTANT_ID, "assistant") if RNG.random() < 0.32 else (DOCTOR_ID, "doctor")
                carry = vi == len(days) - 1 and len(days) >= 3 and RNG.random() < 0.5
                note = CARRY_NOTE if carry else RNG.choice(NOTES)
                sid, _ = make_visit(db, patient, days_ago, creator, role, note)
                # Leave a few recent visits in needs_review as an edge case; verify the rest later.
                if vi == 0 and days_ago <= 20 and len(needs_review_ids) < 3 and RNG.random() < 0.5:
                    needs_review_ids.append(sid)
                else:
                    real_visit_ids.append(sid)

        # Unassigned captures (no patient) — a live "needs attention" signal.
        for _ in range(5):
            s = Session(tenant_id=DEV_TENANT_ID, patient_id=None, status=SessionStatus.unassigned, title="ثبت تخصیص‌نیافته",
                        organization_source=OrganizationSource.none, created_by_user_id=DOCTOR_ID, captured_at=clinic_dt(RNG.randint(0, 5)))
            db.add(s); db.flush()
            db.add(Capture(tenant_id=DEV_TENANT_ID, session_id=s.id, patient_id=None, capture_type=CaptureType.note,
                           status=CaptureStatus.received, client_capture_id=f"ins-un-{uuid.uuid4()}",
                           capture_metadata={"detail": "یادداشت بدون بیمار"}, captured_at=s.captured_at,
                           created_at=s.captured_at, created_by_user_id=DOCTOR_ID))
        # One failed session.
        if seeded_patients:
            fs = Session(tenant_id=DEV_TENANT_ID, patient_id=seeded_patients[0], status=SessionStatus.failed, title="پردازش ناموفق",
                         organization_source=OrganizationSource.none, created_by_user_id=DOCTOR_ID, captured_at=clinic_dt(1), created_at=clinic_dt(1))
            db.add(fs); db.flush()
            db.add(Capture(tenant_id=DEV_TENANT_ID, session_id=fs.id, patient_id=seeded_patients[0], capture_type=CaptureType.note,
                           status=CaptureStatus.needs_attention, client_capture_id=f"ins-fail-{uuid.uuid4()}",
                           capture_metadata={"detail": "پردازش ناموفق"}, captured_at=fs.captured_at, created_at=fs.captured_at, created_by_user_id=DOCTOR_ID))
        db.commit()

        # Wait for the REAL synthesis jobs to land treatments (poll up to ~12 min).
        all_ids = real_visit_ids + needs_review_ids
        print(f"Created {created} patients / {len(all_ids)} visits. Waiting for real AI synthesis…")
        deadline = time.monotonic() + 720
        done = set()
        while time.monotonic() < deadline and len(done) < len(all_ids):
            time.sleep(10)
            db.expire_all()
            for sid in all_ids:
                if sid in done:
                    continue
                s = db.get(Session, sid)
                if (s.extracted_metadata or {}).get("treatments"):
                    done.add(sid)
            print(f"  synthesized {len(done)}/{len(all_ids)}")

        # Finalize: mark the reviewed visits verified so they don't sit in the needs-review tile.
        for sid in real_visit_ids:
            s = db.get(Session, sid)
            if s and s.status in {SessionStatus.needs_review, SessionStatus.organized, SessionStatus.draft}:
                s.status = SessionStatus.verified
                s.verified_at = s.captured_at
                s.verified_by_user_id = s.created_by_user_id
        db.commit()

        # A few REAL patient-memory (Job-4) jobs over returning patients.
        mem = 0
        for pid in seeded_patients[:6]:
            patient = db.get(Patient, pid)
            sessions = list(db.query(Session).filter(Session.tenant_id == DEV_TENANT_ID, Session.patient_id == pid).all())
            if len(sessions) >= 2 and maybe_refresh_stale_patient_memory(
                db, tenant_id=DEV_TENANT_ID, patient=patient, sessions=sessions, created_by_user_id=DOCTOR_ID):
                mem += 1
        db.commit()
        print(f"Done: +{created} patients ({skipped} skipped), {len(done)}/{len(all_ids)} visits synthesized, "
              f"{len(needs_review_ids)} left in review, patient-memory jobs: {mem}.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
