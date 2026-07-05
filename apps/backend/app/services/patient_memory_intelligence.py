"""Mock patient-memory intelligence: a tier-aware patient *summary* (card) + *history* (detail).

This is a PLACEHOLDER for a future AI job — no real AI runs here. The flow it imitates:

1. A content change (a new/removed capture, an assignment) calls :func:`mark_patient_memory_updating`,
   which flips the patient's stored memory to ``updating`` and arms a ``ready_at`` a few seconds out
   (``MOCK_MEMORY_DELAY_SECONDS``) to imitate job latency. Prior finalized content stays visible.
2. The next read after ``ready_at`` calls :func:`finalize_patient_memory_if_due`, which writes the
   deterministic, tier-aware canned content and flips status back to ``ready``.

Tier shapes the *content*, never the tone:

* **Pro** reads as a synthesized, assistant-voiced brief (Snapshot / Story so far / Worth remembering
  / Right now). Source ``mock-ai``. The card summary is a warm one-liner.
* **Basic** reads as a faithful *structural* recap (visit counts, dates, capture types) — never a
  topic guessed from audio, because Basic has no summarization. Source ``mock-deterministic``.

The card ``summary`` is persisted (it powers the list + its updating lifecycle). The richer
``history`` is generated on read in the detail endpoint (one patient at a time), so it is never
stored. The frontend keeps showing prior content under an "Organizing memory" cue until status flips.

Language note: content is English for now. A future ``tenants.assistant_language`` axis (separate
from transcription/report language) will localize this; wiring that is deferred.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import AiJob, AiJobStatus, AiJobType, Patient, Session, Tenant
from app.services.treatment_overlay import effective_treatments

# Imitated AI-job latency. Short enough that the "updating → ready" transition is quick but visible,
# and lands within the frontend's processing-refresh poll ladder.
MOCK_MEMORY_DELAY_SECONDS = 4

MOCK_AI_SOURCE = "mock-ai"
MOCK_DETERMINISTIC_SOURCE = "mock-deterministic"

_TYPE_PHRASE = {
    "audio": "an audio note",
    "photo": "a photo",
    "note": "a written note",
}


# --------------------------------------------------------------------------- helpers


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _memory(patient: Patient) -> dict[str, Any] | None:
    return patient.memory if isinstance(patient.memory, dict) else None


def _session_sort_date(session: Session) -> datetime | None:
    return session.captured_at or session.updated_at or session.created_at


def _capture_count(session: Session) -> int:
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    value = metadata.get("capture_count")
    return value if isinstance(value, int) and value >= 0 else 0


def _latest_type_phrase(session: Session) -> str:
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    latest = metadata.get("latest_capture_type")
    return _TYPE_PHRASE.get(latest if isinstance(latest, str) else "", "a capture")


def _has_audio(session: Session) -> bool:
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    return metadata.get("latest_capture_type") == "audio"


def _fmt_date(value: datetime | None) -> str:
    if value is None:
        return "recently"
    value = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return f"{value:%b} {value.day}"


def _fmt_time(value: datetime | None) -> str | None:
    if value is None:
        return None
    value = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return f"{value:%H:%M}"


def _ordered(sessions: list[Session]) -> list[Session]:
    """Newest-first, by visit time."""
    return sorted(sessions, key=lambda s: _session_sort_date(s) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


def _clip_sentences(text: str | None, max_sentences: int) -> str:
    """Keep at most ``max_sentences`` sentences (the compact line-up card stays glanceable)."""
    if not isinstance(text, str) or not text.strip():
        return ""
    parts = re.split(r"(?<=[.!?。؟])\s+", text.strip())
    return " ".join(parts[:max_sentences]).strip()


# --------------------------------------------------------------------------- read helpers


def tenant_tier(db: DbSession, tenant_id: uuid.UUID) -> str:
    """Return the tenant's intelligence tier ('basic'|'pro'); memory artifacts are AI on Pro only.

    Fail-closed (M-P12): an unknown/missing tier resolves to ``basic``, never Pro — a Basic tenant
    must never be served (or dispatched) a Pro AI memory on account of a bad tier string.
    """
    tier = db.execute(select(Tenant.tier).where(Tenant.id == tenant_id)).scalar_one_or_none()
    return tier if tier in {"basic", "pro"} else "basic"


def memory_status(patient: Patient) -> str:
    mem = _memory(patient)
    return "updating" if mem and mem.get("status") == "updating" else "ready"


def memory_mode(patient: Patient) -> str | None:
    """The tier a patient's stored memory was written for ('pro'|'basic'), if any."""
    mem = _memory(patient)
    mode = mem.get("mode") if mem else None
    return mode if mode in {"pro", "basic"} else None


def memory_matches_tier(patient: Patient, tier: str) -> bool:
    """Whether the stored memory was written for the tenant's CURRENT tier (M-P12).

    A tier flip leaves the prior tier's persisted content behind (a Pro AI summary on a now-Basic
    tenant, or a Basic mock on a now-Pro tenant); callers must not serve mismatched content. Memory
    with no recorded mode (legacy / not yet built) is treated as matching so the rule-based fallback
    still shows something.
    """
    mode = memory_mode(patient)
    return mode is None or mode == tier


def persisted_summary(patient: Patient) -> str | None:
    mem = _memory(patient)
    if mem and isinstance(mem.get("summary"), str) and mem["summary"].strip():
        return mem["summary"].strip()
    return None


def memory_source(patient: Patient) -> str | None:
    mem = _memory(patient)
    return mem.get("source") if mem and isinstance(mem.get("source"), str) else None


def stored_history(patient: Patient) -> dict[str, Any] | None:
    """Return the patient's persisted history brief, if one has been generated."""
    mem = _memory(patient)
    if mem and isinstance(mem.get("history"), dict):
        return mem["history"]
    return None


def patient_has_active_memory_job(db: DbSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID) -> bool:
    """Whether a patient_memory AI job is already queued/running for this patient (dedup guard)."""
    row = db.execute(
        select(AiJob.id)
        .where(
            AiJob.tenant_id == tenant_id,
            AiJob.patient_id == patient_id,
            AiJob.job_type == AiJobType.patient_memory,
            AiJob.status.in_([AiJobStatus.queued, AiJobStatus.running]),
        )
        .limit(1)
    ).scalar_one_or_none()
    return row is not None


def patient_has_pending_capture_jobs(db: DbSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID) -> bool:
    """Whether any of the patient's sessions still has a capture job in flight (report not settled)."""
    session_ids = [row[0] for row in db.execute(
        select(Session.id).where(Session.tenant_id == tenant_id, Session.patient_id == patient_id)
    ).all()]
    if not session_ids:
        return False
    row = db.execute(
        select(AiJob.id)
        .where(
            AiJob.tenant_id == tenant_id,
            AiJob.session_id.in_(session_ids),
            AiJob.capture_id.isnot(None),
            AiJob.status.in_([AiJobStatus.queued, AiJobStatus.running]),
        )
        .limit(1)
    ).scalar_one_or_none()
    return row is not None


def patient_capture_jobs_parked(db: DbSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID) -> bool:
    """Whether a blocking capture job for this patient is PARKED by the fair-use budget gate (M-P6).

    A parked job stays ``queued`` (never sent to Celery) with ``ai_usage_deferred`` set, so it keeps
    ``patient_has_pending_capture_jobs`` True and memory frozen in ``updating`` for as long as the
    budget is exhausted. Callers surface a usage-limit reason instead of an eternal spinner.
    """
    session_ids = [row[0] for row in db.execute(
        select(Session.id).where(Session.tenant_id == tenant_id, Session.patient_id == patient_id)
    ).all()]
    if not session_ids:
        return False
    rows = db.execute(
        select(AiJob.result_metadata).where(
            AiJob.tenant_id == tenant_id,
            AiJob.session_id.in_(session_ids),
            AiJob.capture_id.isnot(None),
            AiJob.status.in_([AiJobStatus.queued, AiJobStatus.running]),
        )
    ).all()
    return any(isinstance(row[0], dict) and row[0].get("ai_usage_deferred") for row in rows)


def memory_status_reason(db: DbSession, *, tenant_id: uuid.UUID, patient: Patient) -> str | None:
    """A machine-readable reason for a stuck ``updating`` memory the UI can map (M-P6).

    ``"usage_limit"`` when the block is a fair-use-parked capture job (so the frontend shows the
    usage-limit state and resumes polling with backoff instead of a static spinner). ``None`` for an
    ordinary in-flight rebuild.
    """
    if memory_status(patient) != "updating":
        return None
    if patient_capture_jobs_parked(db, tenant_id=tenant_id, patient_id=patient.id):
        return "usage_limit"
    return None


def can_finalize_on_read(db: DbSession, *, tenant_id: uuid.UUID, patient: Patient, tier: str) -> bool:
    """Whether a read may deterministically finalize an `updating` memory.

    Basic always may (memory is deterministic). Pro normally waits for its AI job, so a read finalizes
    only when nothing is in flight (no memory job and no capture jobs) — a safety net so Pro memory is
    never permanently stuck in `updating` if a job failed terminally or was never dispatched.
    """
    if tier != "pro":
        return True
    return not patient_has_active_memory_job(db, tenant_id=tenant_id, patient_id=patient.id) and not patient_has_pending_capture_jobs(
        db, tenant_id=tenant_id, patient_id=patient.id
    )


def memory_updated_at(patient: Patient) -> str | None:
    mem = _memory(patient)
    return mem.get("updated_at") if mem and isinstance(mem.get("updated_at"), str) else None


def _session_changed_at(session: Session) -> datetime | None:
    """When a session's content last changed (for memory-staleness comparison)."""
    return session.updated_at or session.created_at or session.captured_at


def _sessions_changed_at(sessions: list[Session]) -> datetime | None:
    """The newest content-change time across a patient's sessions (None when there are none)."""
    return max((changed for session in sessions if (changed := _session_changed_at(session))), default=None)


def _memory_built_session_ids(patient: Patient) -> set[str] | None:
    """The set of session ids the current memory was last built from, if recorded (else None)."""
    mem = _memory(patient)
    ids = mem.get("built_from_sessions") if isinstance(mem, dict) else None
    return {str(i) for i in ids} if isinstance(ids, list) else None


def memory_build_snapshot(patient: Patient, sessions: list[Session], *, now: datetime | None = None) -> dict[str, Any]:
    """Freeze the identity of the inputs a memory build reads, at build-START time (INV-SNAPSHOT).

    Carried from payload-build to completion and written verbatim onto the finalized memory, so its
    freshness means "inputs as of build T", never "completed at T". Records the newest content-change
    time (``updated_at``), the exact session-id set, and the patient's name at build — the three
    signals :func:`patient_memory_is_stale` consults to detect a change that landed *after* the build
    started (an added/edited visit, a reassignment/de-effect that removed one, a rename).
    """
    changed = _sessions_changed_at(sessions)
    return {
        "updated_at": _iso(changed or now or _now()),
        "session_ids": sorted(str(session.id) for session in sessions),
        "display_name": patient.display_name,
    }


def patient_memory_is_stale(patient: Patient, sessions: list[Session]) -> bool:
    """Whether the patient's memory no longer reflects its inputs (→ a refresh is due).

    Drives both triggers that replaced the per-capture dispatch: the read-trigger (patient page /
    line-up opens) and the quiescence sweep. "Built" means a completed memory write — its
    ``updated_at`` is only stamped on finalize/apply, never while ``updating`` — so a refresh that
    is mid-flight still reads as stale, and the per-patient dedup (not this check) prevents a
    duplicate dispatch. A patient with no visits is never stale; a patient with visits but no
    memory yet always is.

    Three change signals, matching the build snapshot (:func:`memory_build_snapshot`):
    * a visit's content changed *after* the build (addition/edit) — ``updated_at`` comparison;
    * the session-id SET changed (a reassignment/de-effect removed one, or one was added) — this is
      what makes a former patient's memory stale on reassignment (M-P2); removals never move any
      remaining session's timestamp, so the set is the only signal;
    * the patient was renamed since the build (M-P9), so cached prose/name is refreshed.
    """
    if not sessions:
        return False
    last_built = _parse_iso(memory_updated_at(patient))
    if last_built is None:
        return True
    latest_change = _sessions_changed_at(sessions)
    if latest_change is not None and latest_change > last_built:
        return True
    built_ids = _memory_built_session_ids(patient)
    if built_ids is not None and built_ids != {str(session.id) for session in sessions}:
        return True
    mem = _memory(patient)
    built_name = mem.get("built_from_name") if isinstance(mem, dict) else None
    if isinstance(built_name, str) and built_name != (patient.display_name or ""):
        return True
    return False


# --------------------------------------------------------------------------- content generators


def generate_patient_memory(
    patient: Patient,
    sessions: list[Session],
    tier: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the deterministic, tier-aware canned memory for a patient.

    Returns ``{mode, summary, source, history}`` where ``history`` is
    ``{mode, snapshot, sections, visits, source}`` (Pro fills ``sections``; Basic fills ``visits``).
    """
    is_pro = tier == "pro"
    ordered = _ordered(sessions)
    count = len(ordered)
    latest = ordered[0] if ordered else None
    first = ordered[-1] if ordered else None
    # The patient's name is shown next to the card/avatar, so the copy never repeats it (redundant).
    visits_word = f"{count} visit" if count == 1 else f"{count} visits"

    if is_pro:
        content = _pro_content(count, visits_word, latest, first)
        source = MOCK_AI_SOURCE
    else:
        content = _basic_content(count, visits_word, latest, first, ordered)
        source = MOCK_DETERMINISTIC_SOURCE

    return {
        "mode": tier if is_pro else "basic",
        "summary": content["summary"],
        "source": source,
        "history": {
            "mode": "pro" if is_pro else "basic",
            "snapshot": content["snapshot"],
            "sections": content.get("sections", []),
            "visits": content.get("visits", []),
            "source": source,
        },
        # The compact line-up-card projection (Pro only). Deterministic here; the AI job overwrites
        # the text parts. hero/delta/flags are layered on at read time by the detail endpoint.
        "card": content.get("card") if is_pro else None,
    }


def _pro_content(
    count: int,
    visits_word: str,
    latest: Session | None,
    first: Session | None,
) -> dict[str, Any]:
    if latest is None or first is None:
        return {
            "summary": "No visits have been captured yet.",
            "snapshot": "No visits captured yet.",
            "sections": [
                {"label": "Story so far", "body": "No visit has been captured yet."},
                {"label": "Worth remembering", "body": "Captures from the first visit will start building this history."},
                {"label": "Right now", "body": "Start a visit to begin building this memory."},
            ],
            "card": {
                "storySoFar": "No visit has been captured yet.",
                "rightNow": "Start a visit to begin building this memory.",
                "flags": [],
            },
        }
    latest_date = _fmt_date(_session_sort_date(latest))
    first_date = _fmt_date(_session_sort_date(first))
    latest_phrase = _latest_type_phrase(latest)
    span = f"since {first_date}" if count > 1 else f"on {first_date}"
    summary = (
        f"{visits_word.capitalize()} on record, most recently {latest_phrase} on {latest_date} — "
        "all captured and organized."
    )
    if count > 1:
        story = (
            f"Memory spans {visits_word} {span}, each visit captured and folded in. The most recent, "
            f"on {latest_date}, came in as {latest_phrase} and has been saved."
        )
        remember = (
            "Visits have been regular, so continuity matters here — each builds on the last. "
            "I'll keep surfacing anything that needs your attention."
        )
    else:
        story = f"This memory starts with the visit on {first_date}, captured as {latest_phrase} and saved."
        remember = "This is an early record — the picture will fill in as more visits are captured."
    now_line = f"Everything from the {latest_date} visit is captured and organized for your review."
    return {
        "summary": summary,
        "snapshot": f"{visits_word.capitalize()} on record, most recently on {latest_date}.",
        "sections": [
            {"label": "Story so far", "body": story},
            {"label": "Worth remembering", "body": remember},
            {"label": "Right now", "body": now_line},
        ],
        "card": {
            "storySoFar": _clip_sentences(story, 2),
            "rightNow": _clip_sentences(now_line, 2),
            "flags": [],
        },
    }


def _basic_content(
    count: int,
    visits_word: str,
    latest: Session | None,
    first: Session | None,
    ordered: list[Session],
) -> dict[str, Any]:
    if latest is None or first is None:
        return {
            "summary": "No visits on record yet.",
            "snapshot": "No visits on record yet.",
            "visits": [],
        }
    latest_date = _fmt_date(_session_sort_date(latest))
    first_date = _fmt_date(_session_sort_date(first))
    latest_count = _capture_count(latest)
    latest_phrase = _latest_type_phrase(latest)
    if latest_count:
        capture_word = "capture" if latest_count == 1 else "captures"
        summary = (
            f"{visits_word.capitalize()} on record since {first_date}. Most recent on {latest_date}: "
            f"{latest_count} {capture_word} saved ({latest_phrase} most recent)."
        )
    else:
        summary = f"{visits_word.capitalize()} on record since {first_date}. Last seen {latest_date}."
    snapshot = f"{visits_word.capitalize()} on record, since {first_date}. Last seen {latest_date}."
    visits: list[str] = []
    for session in ordered[:6]:
        date_text = _fmt_date(_session_sort_date(session))
        time_text = _fmt_time(_session_sort_date(session))
        when = f"{date_text} · {time_text}" if time_text else date_text
        n = _capture_count(session)
        phrase = _latest_type_phrase(session)
        if n:
            capture_word = "capture" if n == 1 else "captures"
            line = f"{when} — {n} {capture_word} saved ({phrase} most recent)."
        else:
            line = f"{when} — visit saved."
        if _has_audio(session):
            line += " Transcript saved — open the visit to read it."
        visits.append(line)
    return {"summary": summary, "snapshot": snapshot, "visits": visits}


# --------------------------------------------------------------------------- lifecycle


def mark_patient_memory_updating(
    db: DbSession,
    patient_id: uuid.UUID | None,
    *,
    now: datetime | None = None,
) -> None:
    """Flag a patient's memory as refreshing after a content change.

    Keeps any prior finalized content visible; only flips status + arms ``ready_at``. Cheap and
    idempotent. The caller is responsible for committing.
    """
    if patient_id is None:
        return
    patient = db.get(Patient, patient_id)
    if patient is None:
        return
    moment = now or _now()
    mem = _memory(patient) or {}
    patient.memory = {
        **mem,
        "status": "updating",
        "updating_since": _iso(moment),
        "ready_at": _iso(moment + timedelta(seconds=MOCK_MEMORY_DELAY_SECONDS)),
    }


def finalize_patient_memory_if_due(
    db: DbSession,
    patient: Patient,
    sessions: list[Session],
    tier: str,
    *,
    now: datetime | None = None,
) -> bool:
    """Settle a memory stuck in ``updating`` past its imitated latency. Tier-aware.

    Basic memory *is* deterministic, so this writes the canned content and flips to ``ready``,
    stamping freshness from the inputs snapshot (INV-SNAPSHOT), not completion time.

    Pro memory is written by the async AI job; this is only the read-path SAFETY NET (see
    ``can_finalize_on_read``). It MUST NEVER fabricate canned content over a real AI memory (M-P1):
    it only de-spins the status back to ``ready`` while preserving the prior summary/history/card,
    and it deliberately leaves ``updated_at`` untouched so the memory stays *stale* and the AI
    rebuild is still due (the read-trigger / line-up / sweep dispatches it). Returns True on change.
    """
    mem = _memory(patient)
    if not mem or mem.get("status") != "updating":
        return False
    moment = now or _now()
    ready_at = _parse_iso(mem.get("ready_at"))
    if ready_at is not None and moment < ready_at:
        return False
    if tier == "pro":
        # De-spin only — keep every prior content key, drop the updating markers, never re-stamp
        # updated_at. If no real memory was ever built, the prior content is simply empty and the
        # read-trigger's ``maybe_refresh_stale_patient_memory`` dispatches the first AI build.
        preserved = {
            key: value for key, value in mem.items() if key not in {"status", "updating_since", "ready_at"}
        }
        patient.memory = {**preserved, "status": "ready"}
        return True
    content = generate_patient_memory(patient, sessions, tier, now=moment)
    snapshot = memory_build_snapshot(patient, sessions, now=moment)
    patient.memory = {
        "status": "ready",
        "mode": content["mode"],
        "summary": content["summary"],
        "history": content["history"],
        "card": None,
        "source": content["source"],
        "updated_at": snapshot["updated_at"],
        "built_from_sessions": snapshot["session_ids"],
        "built_from_name": snapshot["display_name"],
    }
    return True


# --------------------------------------------------------------------------- real AI job (Pro)


# Treatment fields fed to the memory model: the queryable core that grounds recall ("last used
# Voluma 0.3 mL, left cheek"). quantityText is kept verbatim (original script) for display/audit.
_TREATMENT_BRIEF_KEYS = ("area", "product", "brand", "quantity", "unit", "quantityText", "lot")


def _session_treatments(session: Session, *, limit: int = 8) -> list[dict[str, Any]]:
    """Compact per-visit treatments for grounding — read the OVERLAID treatments so the memory brief
    quotes a clinician-corrected dose/lot, not the raw AI artifact (AES-1101, the lot-recall safety case)."""
    treatments: list[dict[str, Any]] = []
    for item in effective_treatments(session)[:limit]:
        compact = {key: item.get(key) for key in _TREATMENT_BRIEF_KEYS if item.get(key) not in (None, "")}
        if compact:
            treatments.append(compact)
    return treatments


def _session_brief(session: Session) -> dict[str, Any]:
    """A compact, distilled per-visit brief fed to the patient-memory model (not raw transcripts)."""
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    summaries = metadata.get("summaries") if isinstance(metadata.get("summaries"), dict) else {}
    summary = session.generated_summary or session.summary or summaries.get("short")
    return {
        "date": _iso(_session_sort_date(session)),
        "captureCount": _capture_count(session),
        "latestType": metadata.get("latest_capture_type") if isinstance(metadata.get("latest_capture_type"), str) else None,
        "summary": summary.strip() if isinstance(summary, str) and summary.strip() else None,
        # Each visit's performed treatments, so recall is grounded in real doses/products/areas.
        "treatments": _session_treatments(session),
    }


def build_patient_memory_job_input(
    patient: Patient,
    sessions: list[Session],
    tier: str,
    *,
    language: str | None = None,
    domain: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the worker payload for the combined patient-memory job.

    Incremental by design: the model gets the **prior** memory plus compact per-visit briefs (the
    session stage already distilled these), not raw transcripts — so cost stays ~flat as visits
    grow. A `deterministicFallback` is included so a gateway-less worker still returns valid content.
    ``domain`` carries vertical-aware prompt framing (label); the worker falls back to a neutral
    "clinic" when it is absent, so the prompt never hardcodes a vertical.
    """
    ordered = _ordered(sessions)
    prior = _memory(patient)
    prior_brief = None
    if prior and (prior.get("summary") or prior.get("history")):
        prior_brief = {"summary": prior.get("summary"), "history": prior.get("history")}
    fallback = generate_patient_memory(patient, sessions, tier)
    return {
        "tier": tier,
        "language": language,
        "domain": domain,
        "patient": {
            # The patient's name is deliberately NOT sent to the model (M-P9): memory prose must
            # never bake in a name that a later rename would strand — it is shown beside the text
            # in the UI. The prompt reinforces "do not include the name".
            "visitCount": len(ordered),
            "firstSeen": _iso(_session_sort_date(ordered[-1])) if ordered else None,
            "priorMemory": prior_brief,
            "sessions": [_session_brief(session) for session in ordered[:8]],
        },
        "deterministicFallback": {
            "summary": fallback["summary"],
            "history": fallback["history"],
            "source": fallback["source"],
            "card": fallback.get("card"),
        },
    }


def _coerce_history(history: Any, tier: str) -> dict[str, Any]:
    """Normalize a (possibly model-authored) history object into the stable stored shape."""
    history = history if isinstance(history, dict) else {}
    sections = [
        {"label": str(section.get("label", "")), "body": str(section.get("body", ""))}
        for section in (history.get("sections") if isinstance(history.get("sections"), list) else [])
        if isinstance(section, dict) and section.get("body")
    ]
    visits = [str(visit) for visit in (history.get("visits") if isinstance(history.get("visits"), list) else []) if isinstance(visit, str)]
    return {
        "mode": "pro" if tier == "pro" else "basic",
        "snapshot": str(history.get("snapshot", "")),
        "sections": sections,
        "visits": visits,
        "source": str(history.get("source", "")) or (MOCK_AI_SOURCE if tier == "pro" else MOCK_DETERMINISTIC_SOURCE),
    }


# Surfaced line-up flags a clinician should see at a glance; anything else is normalized to "caution".
_FLAG_KINDS = frozenset({"allergy", "consent", "preference", "caution"})


def stored_card(patient: Patient) -> dict[str, Any] | None:
    """Return the patient's persisted line-up-card text (storySoFar/rightNow/flags), if any."""
    mem = _memory(patient)
    card = mem.get("card") if mem else None
    return card if isinstance(card, dict) else None


def _coerce_flags(value: Any) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        if not label:
            continue
        kind = str(item.get("kind", "")).strip().lower()
        flags.append({"kind": kind if kind in _FLAG_KINDS else "caution", "label": label[:120]})
    return flags[:4]


def _coerce_card(card: Any, *, fallback: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Normalize a (model- or deterministically-authored) line-up card; None when it carries nothing.

    Enforces the compact contract here so a verbose model never leaks into the glanceable card:
    ``storySoFar``/``rightNow`` are each clipped to 2 sentences. Empty fields fall back to the
    deterministic card so the Pro line-up is never blank.
    """
    card = card if isinstance(card, dict) else {}
    fallback = fallback if isinstance(fallback, dict) else {}
    story = _clip_sentences(card.get("storySoFar"), 2) or _clip_sentences(fallback.get("storySoFar"), 2)
    right_now = _clip_sentences(card.get("rightNow"), 2) or _clip_sentences(fallback.get("rightNow"), 2)
    flags = _coerce_flags(card.get("flags")) or _coerce_flags(fallback.get("flags"))
    if not (story or right_now or flags):
        return None
    return {"storySoFar": story, "rightNow": right_now, "flags": flags}


def card_from_history(history: Any) -> dict[str, Any] | None:
    """Derive a deterministic line-up card from a stored history brief (read-time fallback)."""
    history = history if isinstance(history, dict) else {}
    sections = history.get("sections") if isinstance(history.get("sections"), list) else []
    by_label = {
        str(section.get("label", "")).strip().lower(): section.get("body")
        for section in sections
        if isinstance(section, dict)
    }
    return _coerce_card(
        {
            "storySoFar": by_label.get("story so far") or history.get("snapshot"),
            "rightNow": by_label.get("right now"),
            "flags": [],
        }
    )


def apply_patient_memory_output(
    patient: Patient,
    output: dict[str, Any],
    tier: str,
    *,
    now: datetime | None = None,
    snapshot: dict[str, Any] | None = None,
) -> None:
    """Write a completed patient-memory job's output onto the patient (status → ready).

    ``snapshot`` is the build-START inputs snapshot (:func:`memory_build_snapshot`), carried on the
    job. Its ``updated_at`` becomes the memory's freshness (INV-SNAPSHOT / M-P5) — so a visit that
    changed *while the job ran* leaves ``session.updated_at`` newer than the memory and the memory
    reads as stale — and its session-id set + name are recorded so a later reassignment/rename marks
    the memory stale (M-P2 / M-P9). Absent a snapshot (recovery, legacy), freshness falls back to
    completion time.
    """
    moment = now or _now()
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    summary = output.get("summary")
    history = output.get("history")
    source = output.get("source") if isinstance(output.get("source"), str) and output.get("source") else None
    card = output.get("card")
    if not isinstance(summary, str) or not summary.strip() or not isinstance(history, dict):
        # Defensive: the worker is expected to fall back to deterministic content, but guard anyway.
        fallback = generate_patient_memory(patient, [], tier, now=moment)
        summary, history, source, card = fallback["summary"], fallback["history"], fallback["source"], fallback.get("card")
    coerced_history = _coerce_history(history, tier)
    updated_at = snapshot.get("updated_at") if isinstance(snapshot.get("updated_at"), str) else _iso(moment)
    patient.memory = {
        "status": "ready",
        "mode": "pro" if tier == "pro" else "basic",
        "summary": summary.strip(),
        "history": coerced_history,
        # Line-up card text is a Pro artifact; deterministic-history fallback keeps it populated.
        "card": _coerce_card(card, fallback=card_from_history(coerced_history)) if tier == "pro" else None,
        "source": source or (MOCK_AI_SOURCE if tier == "pro" else MOCK_DETERMINISTIC_SOURCE),
        "updated_at": updated_at,
        "built_from_sessions": snapshot.get("session_ids") if isinstance(snapshot.get("session_ids"), list) else None,
        "built_from_name": snapshot.get("display_name") if isinstance(snapshot.get("display_name"), str) else None,
    }
