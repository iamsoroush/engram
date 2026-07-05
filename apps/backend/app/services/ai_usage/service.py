"""Fair-use AI metering + enforcement.

Records REAL gateway spend per clinic/seat/period, exposes the clinic's usage state for the UI, and
answers the one enforcement question the dispatch chokepoints ask: *may background AI enrichment run
right now?* Capture is NEVER gated here — only the dispatch of background enrichment jobs is, so a
capture always saves and its enrichment simply queues until the next period (or a top-up/upgrade).
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session as DbSession

from app.models import AiJob, AiJobType, AiUsageCounter, Capture, CaptureStatus
from app.services.ai_usage.plans import PlanBudget, budget_per_seat_usd, resolve_plan_budget
from app.services.ai_usage.pricing import audio_seconds_from_records, usage_records_cost_micros

# Job types that count as an "AI capture" (per-capture pipeline). Text is free but still a capture.
_CAPTURE_JOB_TYPES = {
    AiJobType.capture_process,
    AiJobType.audio_capture_process,
    AiJobType.text_capture_process,
    AiJobType.image_capture_process,
}
_SYNTHESIS_JOB_TYPES = {AiJobType.session_organize}
# Post-session patient Q&A jobs (AES-402). Their real gateway spend is metered like any other job (so
# the fair-use budget accounts for it and the pause applies — Q-8); they are neither a "capture" nor a
# "synthesis" for the per-job counters, but they DO count as an AI job so a zero-cost fallback is still
# tallied. Dispatch enforcement lives in ``services.qa`` (it pauses drafting when over budget).
_QA_JOB_TYPES = {AiJobType.qa_draft, AiJobType.qa_revise}


def current_period_key(now: datetime | None = None) -> str:
    """Calendar-month period key "YYYY-MM" in UTC."""
    moment = now or datetime.now(timezone.utc)
    return moment.strftime("%Y-%m")


def period_reset_at(period_key: str) -> datetime:
    """First instant of the month AFTER the given period (when usage resets), UTC."""
    year, month = (int(part) for part in period_key.split("-"))
    return (
        datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        if month == 12
        else datetime(year, month + 1, 1, tzinfo=timezone.utc)
    )


# --- Metering -----------------------------------------------------------------


def record_job_usage(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    job_type: AiJobType,
    usage_records: list[dict] | None,
) -> int:
    """Accumulate one completed job's real usage into the clinic/seat period counter.

    Returns the cost recorded (micro-dollars). Best-effort: metering must never break job completion.
    """
    cost_micros = usage_records_cost_micros(usage_records)
    audio_seconds = audio_seconds_from_records(usage_records)
    is_capture = job_type in _CAPTURE_JOB_TYPES
    is_synthesis = job_type in _SYNTHESIS_JOB_TYPES
    is_qa = job_type in _QA_JOB_TYPES
    if cost_micros == 0 and not is_capture and not is_synthesis and not is_qa and audio_seconds == 0:
        return 0
    period_key = current_period_key()
    stmt = pg_insert(AiUsageCounter).values(
        tenant_id=tenant_id,
        user_id=user_id,
        period_key=period_key,
        cost_micros=cost_micros,
        ai_captures=1 if is_capture else 0,
        audio_seconds=audio_seconds,
        synthesis_runs=1 if is_synthesis else 0,
        ai_jobs=1,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["tenant_id", "user_id", "period_key"],
        set_={
            "cost_micros": AiUsageCounter.cost_micros + cost_micros,
            "ai_captures": AiUsageCounter.ai_captures + (1 if is_capture else 0),
            "audio_seconds": AiUsageCounter.audio_seconds + audio_seconds,
            "synthesis_runs": AiUsageCounter.synthesis_runs + (1 if is_synthesis else 0),
            "ai_jobs": AiUsageCounter.ai_jobs + 1,
            "updated_at": func.now(),
        },
    )
    db.execute(stmt)
    db.commit()
    return cost_micros


# --- State + enforcement ------------------------------------------------------


@dataclass(frozen=True)
class ClinicUsageState:
    plan: str
    hasAi: bool
    status: str  # "ok" | "approaching" | "over"
    seats: int
    periodKey: str
    resetAt: str
    budgetUsd: float
    budgetPerSeatUsd: float
    spentUsd: float
    percentUsed: int
    paused: bool
    aiCaptures: int
    audioMinutes: float
    synthesisRuns: int
    sessionSoftCapCaptures: int


def _period_totals(db: DbSession, tenant_id: uuid.UUID, period_key: str) -> tuple[int, int, int, int]:
    """(cost_micros, ai_captures, audio_seconds, synthesis_runs) summed over the clinic's seats."""
    row = db.execute(
        select(
            func.coalesce(func.sum(AiUsageCounter.cost_micros), 0),
            func.coalesce(func.sum(AiUsageCounter.ai_captures), 0),
            func.coalesce(func.sum(AiUsageCounter.audio_seconds), 0),
            func.coalesce(func.sum(AiUsageCounter.synthesis_runs), 0),
        ).where(AiUsageCounter.tenant_id == tenant_id, AiUsageCounter.period_key == period_key)
    ).one()
    return int(row[0]), int(row[1]), int(row[2]), int(row[3])


def clinic_usage_state(db: DbSession, tenant_id: uuid.UUID) -> ClinicUsageState:
    """Resolve the clinic's current-period usage state (for the API + enforcement)."""
    budget: PlanBudget = resolve_plan_budget(db, tenant_id)
    period_key = current_period_key()
    cost_micros, captures, audio_seconds, synthesis_runs = _period_totals(db, tenant_id, period_key)
    spent_usd = cost_micros / 1_000_000.0
    if not budget.has_ai or budget.budget_usd <= 0:
        pct = 0
        status = "ok"
        paused = False
    else:
        pct = int(min(round(spent_usd / budget.budget_usd * 100), 999))
        paused = spent_usd >= budget.budget_usd
        status = "over" if paused else ("approaching" if pct >= int(budget.warn_threshold * 100) else "ok")
    return ClinicUsageState(
        plan=budget.plan,
        hasAi=budget.has_ai,
        status=status,
        seats=budget.seats,
        periodKey=period_key,
        resetAt=period_reset_at(period_key).isoformat(),
        budgetUsd=round(budget.budget_usd, 4),
        budgetPerSeatUsd=round(budget.budget_per_seat_usd, 4),
        spentUsd=round(spent_usd, 6),
        percentUsed=pct,
        paused=paused,
        aiCaptures=captures,
        audioMinutes=round(audio_seconds / 60.0, 1),
        synthesisRuns=synthesis_runs,
        sessionSoftCapCaptures=budget.session_soft_cap_captures,
    )


def clinic_usage_state_dict(db: DbSession, tenant_id: uuid.UUID) -> dict:
    """Client-facing usage state. The raw dollar budget/spend are INTERNAL economics and are NOT
    serialized to the client — the UI only ever shows the percentage + status."""
    data = asdict(clinic_usage_state(db, tenant_id))
    for internal_field in ("budgetUsd", "budgetPerSeatUsd", "spentUsd"):
        data.pop(internal_field, None)
    return data


def enrichment_paused(db: DbSession, tenant_id: uuid.UUID) -> bool:
    """True when the clinic's metered spend has reached its monthly budget (pause background AI)."""
    budget = resolve_plan_budget(db, tenant_id)
    if not budget.has_ai or budget.budget_usd <= 0:
        return False
    cost_micros, _, _, _ = _period_totals(db, tenant_id, current_period_key())
    return (cost_micros / 1_000_000.0) >= budget.budget_usd


def _session_ai_capture_count(db: DbSession, tenant_id: uuid.UUID, session_id: uuid.UUID) -> int:
    return int(
        db.execute(
            select(func.count(Capture.id)).where(
                Capture.tenant_id == tenant_id,
                Capture.session_id == session_id,
                Capture.status != CaptureStatus.deleted,
            )
        ).scalar_one()
        or 0
    )


def should_defer_dispatch(db: DbSession, job: AiJob) -> str | None:
    """Reason to DEFER (not dispatch) this AI job, or None to proceed.

    The one gate the dispatch chokepoints consult. Never touches the capture itself — the capture is
    already saved; only the background enrichment job waits.
    """
    if enrichment_paused(db, job.tenant_id):
        return "ai_budget_exceeded"
    # Per-session SOFT cap: pause further per-capture enrichment for a single runaway session.
    budget = resolve_plan_budget(db, job.tenant_id)
    if (
        budget.session_soft_cap_captures > 0
        and job.job_type in _CAPTURE_JOB_TYPES
        and job.session_id is not None
        and _session_ai_capture_count(db, job.tenant_id, job.session_id) > budget.session_soft_cap_captures
    ):
        return "session_soft_cap_exceeded"
    return None


def set_dev_usage_percent(db: DbSession, tenant_id: uuid.UUID, percent: float) -> dict:
    """DEV/TEST ONLY: force the clinic's current-period metered spend to ``percent`` of its budget.

    The fast path to reach approaching/at/over-limit states without hundreds of real captures. Writes
    a single clinic-scoped counter row (user_id NULL). Never exposed in production (route-guarded).
    """
    budget = resolve_plan_budget(db, tenant_id)
    target_usd = max(budget.budget_usd, 0.0) * (max(percent, 0.0) / 100.0)
    cost_micros = int(round(target_usd * 1_000_000))
    period_key = current_period_key()
    stmt = pg_insert(AiUsageCounter).values(
        tenant_id=tenant_id, user_id=None, period_key=period_key, cost_micros=cost_micros, ai_jobs=0
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["tenant_id", "user_id", "period_key"],
        set_={"cost_micros": cost_micros, "updated_at": func.now()},
    )
    db.execute(stmt)
    db.commit()
    return clinic_usage_state_dict(db, tenant_id)


def mark_job_deferred(db: DbSession, job: AiJob, reason: str) -> None:
    """Park an AI job (kept queued, NOT sent to Celery) because enrichment is paused.

    Recovery re-attempts dispatch on the beat loop; while paused it re-defers, and it resumes
    automatically once the budget frees (new period / top-up / upgrade). The capture is untouched.
    """
    now = datetime.now(timezone.utc)
    job.retry_reason = reason
    job.result_metadata = {
        **(job.result_metadata or {}),
        "ai_usage_deferred": True,
        "ai_usage_deferred_reason": reason,
        "ai_usage_deferred_at": now.isoformat(),
    }
    db.commit()
