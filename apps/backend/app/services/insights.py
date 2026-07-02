"""Clinic insights (owner/admin analytics).

Deterministic, zero-AI aggregation over the data the platform already captures — activity, retention,
staff productivity, patient panel, and (Pro) treatment/product insights. No new AI job (the eval gate
does not apply); the treatment lenses read the already-extracted
``Session.extracted_metadata["treatments"]`` the same way the smart-lists/lot-ledger surface does.

**Deliberate constraints (no fabricated data):** the system stores no price/cost/invoice/payment and
no appointment/booking, so there are *no* revenue or scheduling/utilization metrics here — only
activity- and clinically-derived numbers. Times are aggregated in **UTC** (there is no per-tenant
timezone yet); the busy-times heatmap notes this.

Design shape mirrors ``services/smart_lists.py``: thin DB loaders assemble in-memory rows, and the
analytically-tricky work lives in **pure functions** (``_*_from_*``) that are unit-tested without a DB.
All reads are tenant-scoped; the router gates them owner/admin, and the treatments payload is
additionally Pro-gated on ``live_report_synthesis``.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.models import (
    Capture,
    CaptureStatus,
    Patient,
    PatientStatus,
    Session,
    SessionStatus,
    TenantMembership,
    MembershipStatus,
    User,
)
from app.services.capabilities import LIVE_REPORT_SYNTHESIS, tenant_has_capability

# --- Tunables ---------------------------------------------------------------------------------------
RECENCY_ACTIVE_DAYS = 90       # last visit < 90d  → active
RECENCY_LAPSING_DAYS = 180     # 90–180d           → lapsing (>180d → lapsed)
WEEK_BUCKET_THRESHOLD_DAYS = 92  # windows longer than this bucket by week, else by day
TOP_N = 12                     # ranked-list caps (top treatments / products / areas)
MIX_TOP_PRODUCTS = 5           # distinct products tracked in the treatment-mix series (+ "other")

RANGE_KEYS = ("this-week", "this-month", "last-3-months", "this-year", "custom")
AGE_BANDS = ("<18", "18-25", "26-35", "36-45", "46-55", "56+")


# --- Time helpers -----------------------------------------------------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _sort_date(captured_at: datetime | None, created_at: datetime | None) -> datetime | None:
    """A visit's clinical anchor: ``captured_at`` else the immutable ``created_at`` (never the mutable
    ``updated_at``) — the same recency rule the smart-lists surface uses."""
    return _aware(captured_at) or _aware(created_at)


@dataclass(frozen=True)
class Window:
    """A time window plus the equal-length preceding window used for deltas, and bucket granularity."""

    start: datetime
    end: datetime
    prev_start: datetime
    prev_end: datetime
    granularity: str  # "day" | "week"
    range_key: str


def _parse_day(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def resolve_window(range_key: str, *, now: datetime, frm: str | None = None, to: str | None = None) -> Window:
    """Resolve a range key (+ optional custom ``from``/``to``) into a :class:`Window`.

    The previous window is always the equal-length span immediately preceding ``start`` — so a delta
    compares like-for-like even for the calendar-to-date ranges (this week/month/year).
    """
    key = range_key if range_key in RANGE_KEYS else "this-month"
    end = now
    if key == "this-week":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    elif key == "this-year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif key == "last-3-months":
        start = now - timedelta(days=90)
    elif key == "custom":
        start = _parse_day(frm) or (now - timedelta(days=30))
        parsed_to = _parse_day(to)
        end = (parsed_to + timedelta(days=1)) if parsed_to else now  # 'to' is an inclusive day
    else:  # this-month
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if end < start:
        end = start
    length = end - start
    granularity = "week" if length.days > WEEK_BUCKET_THRESHOLD_DAYS else "day"
    return Window(start=start, end=end, prev_start=start - length, prev_end=start, granularity=granularity, range_key=key)


def _bucket_start(dt: datetime, granularity: str) -> date:
    d = dt.astimezone(timezone.utc).date()
    if granularity == "week":
        return d - timedelta(days=d.weekday())  # Monday
    return d


def _bucket_sequence(window: Window) -> list[str]:
    """The ordered, gap-free list of bucket keys (ISO dates) spanning the window — so a series chart is
    continuous even where a bucket has no activity."""
    step = timedelta(days=7 if window.granularity == "week" else 1)
    cursor = _bucket_start(window.start, window.granularity)
    last = _bucket_start(window.end, window.granularity)
    keys: list[str] = []
    while cursor <= last:
        keys.append(cursor.isoformat())
        cursor = cursor + step
    return keys or [_bucket_start(window.start, window.granularity).isoformat()]


# --- Normalization helpers (pure) -------------------------------------------------------------------
_FEMALE = {"female", "f", "woman", "زن", "مونث", "مؤنث"}
_MALE = {"male", "m", "man", "مرد", "مذکر"}


def normalize_sex(value: str | None) -> str:
    if not isinstance(value, str) or not value.strip():
        return "unknown"
    token = value.strip().lower()
    if token in _FEMALE:
        return "female"
    if token in _MALE:
        return "male"
    return "other"


def age_band(dob: date | None, today: date) -> str | None:
    if dob is None:
        return None
    years = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if years < 18:
        return "<18"
    if years <= 25:
        return "18-25"
    if years <= 35:
        return "26-35"
    if years <= 45:
        return "36-45"
    if years <= 55:
        return "46-55"
    return "56+"


def recency_bucket(last_visit: datetime | None, now: datetime) -> str | None:
    if last_visit is None:
        return None
    days = (now - _aware(last_visit)).days
    if days < RECENCY_ACTIVE_DAYS:
        return "active"
    if days < RECENCY_LAPSING_DAYS:
        return "lapsing"
    return "lapsed"


def normalize_unit(unit: Any) -> str | None:
    """Fold dose units into a stable family for consumption totals (``cc`` → ``ml``, ``units`` → ``u``)."""
    if not isinstance(unit, str) or not unit.strip():
        return None
    token = unit.strip().lower().rstrip(".")
    if token in {"u", "unit", "units", "iu"}:
        return "u"
    if token in {"ml", "cc", "milliliter", "millilitre"}:
        return "ml"
    if token in {"mg", "milligram"}:
        return "mg"
    return token


def _treatment_name(treatment: dict[str, Any]) -> str | None:
    name = treatment.get("product") or treatment.get("brand")
    return name.strip() if isinstance(name, str) and name.strip() else None


def _treatment_brand(treatment: dict[str, Any]) -> str | None:
    name = treatment.get("brand") or treatment.get("product")
    return name.strip() if isinstance(name, str) and name.strip() else None


# --- In-memory row shapes (what the loaders return; what the pure aggregators consume) ---------------
@dataclass(frozen=True)
class VisitRow:
    session_id: uuid.UUID
    patient_id: uuid.UUID | None
    created_by_user_id: uuid.UUID
    when: datetime
    treatments: list[dict[str, Any]]


@dataclass(frozen=True)
class CaptureRow:
    created_by_user_id: uuid.UUID
    patient_id: uuid.UUID | None
    when: datetime


# --- DB loaders -------------------------------------------------------------------------------------
def _sessions_with_captures(tenant_id: uuid.UUID):
    return select(Capture.session_id).where(
        Capture.tenant_id == tenant_id,
        Capture.status != CaptureStatus.deleted,
    )


def _load_visits(db: DbSession, tenant_id: uuid.UUID, start: datetime, end: datetime) -> list[VisitRow]:
    """Real visits (a session with ≥1 non-deleted capture) whose clinical date falls in ``[start,end)``."""
    when = func.coalesce(Session.captured_at, Session.created_at)
    rows = db.execute(
        select(
            Session.id,
            Session.patient_id,
            Session.created_by_user_id,
            Session.captured_at,
            Session.created_at,
            Session.extracted_metadata,
        ).where(
            Session.tenant_id == tenant_id,
            Session.id.in_(_sessions_with_captures(tenant_id)),
            when >= start,
            when < end,
        )
    ).all()
    visits: list[VisitRow] = []
    for sid, pid, uid, captured_at, created_at, metadata in rows:
        anchor = _sort_date(captured_at, created_at)
        if anchor is None:
            continue
        raw = metadata.get("treatments") if isinstance(metadata, dict) else None
        treatments = [t for t in raw if isinstance(t, dict)] if isinstance(raw, list) else []
        visits.append(VisitRow(session_id=sid, patient_id=pid, created_by_user_id=uid, when=anchor, treatments=treatments))
    return visits


def _load_captures(db: DbSession, tenant_id: uuid.UUID, start: datetime, end: datetime) -> list[CaptureRow]:
    when = func.coalesce(Capture.captured_at, Capture.created_at)
    rows = db.execute(
        select(Capture.created_by_user_id, Capture.patient_id, Capture.captured_at, Capture.created_at).where(
            Capture.tenant_id == tenant_id,
            Capture.status != CaptureStatus.deleted,
            when >= start,
            when < end,
        )
    ).all()
    out: list[CaptureRow] = []
    for uid, pid, captured_at, created_at in rows:
        anchor = _sort_date(captured_at, created_at)
        if anchor is not None:
            out.append(CaptureRow(created_by_user_id=uid, patient_id=pid, when=anchor))
    return out


def _count_new_patients(db: DbSession, tenant_id: uuid.UUID, start: datetime, end: datetime) -> int:
    return db.execute(
        select(func.count(Patient.id)).where(
            Patient.tenant_id == tenant_id,
            Patient.status == PatientStatus.active,
            Patient.created_at >= start,
            Patient.created_at < end,
        )
    ).scalar_one()


def _last_visit_per_patient(db: DbSession, tenant_id: uuid.UUID) -> dict[uuid.UUID, datetime]:
    """Most-recent real-visit date per (active) patient, all-time — the recency-cohort substrate."""
    when = func.coalesce(Session.captured_at, Session.created_at)
    rows = db.execute(
        select(Session.patient_id, func.max(when)).where(
            Session.tenant_id == tenant_id,
            Session.patient_id.isnot(None),
            Session.id.in_(_sessions_with_captures(tenant_id)),
        ).group_by(Session.patient_id)
    ).all()
    return {pid: _aware(last) for pid, last in rows if pid is not None and last is not None}


# --- Overview ---------------------------------------------------------------------------------------
def _delta(current: int, previous: int) -> dict[str, Any]:
    if previous == 0:
        return {"current": current, "previous": previous, "pct": None}
    return {"current": current, "previous": previous, "pct": round((current - previous) / previous * 100, 1)}


def _new_vs_returning(visits: Iterable[VisitRow], window_start: datetime, first_visit_ever: dict[uuid.UUID, datetime]) -> dict[str, Any]:
    """Split patients *seen in the window* into new (first-ever visit is in-window) vs returning."""
    seen: set[uuid.UUID] = set()
    for v in visits:
        if v.patient_id is not None:
            seen.add(v.patient_id)
    new = sum(1 for pid in seen if (first_visit_ever.get(pid) or window_start) >= window_start)
    returning = len(seen) - new
    total = new + returning
    return {"new": new, "returning": returning, "repeatRate": round(returning / total, 3) if total else None}


def _activity_series(visits: list[VisitRow], captures: list[CaptureRow], new_patient_days: list[date], window: Window) -> list[dict[str, Any]]:
    keys = _bucket_sequence(window)
    buckets: dict[str, dict[str, int]] = {k: {"visits": 0, "captures": 0, "newPatients": 0} for k in keys}
    for v in visits:
        buckets.setdefault(_bucket_start(v.when, window.granularity).isoformat(), {"visits": 0, "captures": 0, "newPatients": 0})["visits"] += 1
    for c in captures:
        buckets.setdefault(_bucket_start(c.when, window.granularity).isoformat(), {"visits": 0, "captures": 0, "newPatients": 0})["captures"] += 1
    for d in new_patient_days:
        k = _bucket_start(datetime(d.year, d.month, d.day, tzinfo=timezone.utc), window.granularity).isoformat()
        buckets.setdefault(k, {"visits": 0, "captures": 0, "newPatients": 0})["newPatients"] += 1
    return [{"date": k, **buckets[k]} for k in sorted(buckets)]


def _busy_heatmap(visits: Iterable[VisitRow]) -> list[list[int]]:
    """Dense 7×24 (day-of-week × hour, UTC) matrix of visit counts."""
    grid = [[0] * 24 for _ in range(7)]
    for v in visits:
        local = v.when.astimezone(timezone.utc)
        grid[local.weekday()][local.hour] += 1
    return grid


def get_overview(db: DbSession, principal: CurrentPrincipal, window: Window) -> dict[str, Any]:
    tenant_id = principal.tenant_id
    visits = _load_visits(db, tenant_id, window.start, window.end)
    captures = _load_captures(db, tenant_id, window.start, window.end)
    prev_visits = _load_visits(db, tenant_id, window.prev_start, window.prev_end)
    prev_captures = _load_captures(db, tenant_id, window.prev_start, window.prev_end)

    active_patients = {v.patient_id for v in visits if v.patient_id is not None}
    prev_active = {v.patient_id for v in prev_visits if v.patient_id is not None}
    new_patients = _count_new_patients(db, tenant_id, window.start, window.end)
    prev_new_patients = _count_new_patients(db, tenant_id, window.prev_start, window.prev_end)

    first_visit_ever = _load_first_visit_per_patient(db, tenant_id)
    new_patient_days = _load_new_patient_days(db, tenant_id, window.start, window.end)

    # Live (not windowed) actionable backlog.
    unassigned = db.execute(
        select(func.count(Capture.id)).where(
            Capture.tenant_id == tenant_id, Capture.status != CaptureStatus.deleted, Capture.patient_id.is_(None)
        )
    ).scalar_one()
    awaiting_review = db.execute(
        select(func.count(Session.id)).where(Session.tenant_id == tenant_id, Session.status == SessionStatus.needs_review)
    ).scalar_one()
    failed = db.execute(
        select(func.count(Session.id)).where(Session.tenant_id == tenant_id, Session.status == SessionStatus.failed)
    ).scalar_one()

    return {
        "range": window.range_key,
        "kpis": {
            "visits": _delta(len(visits), len(prev_visits)),
            "newPatients": _delta(new_patients, prev_new_patients),
            "activePatients": _delta(len(active_patients), len(prev_active)),
            "captures": _delta(len(captures), len(prev_captures)),
        },
        "activitySeries": _activity_series(visits, captures, new_patient_days, window),
        "newVsReturning": _new_vs_returning(visits, window.start, first_visit_ever),
        "busyHeatmap": _busy_heatmap(visits),
        "needsAttention": {"unassignedCaptures": unassigned, "awaitingReview": awaiting_review, "failed": failed},
    }


def _load_first_visit_per_patient(db: DbSession, tenant_id: uuid.UUID) -> dict[uuid.UUID, datetime]:
    when = func.coalesce(Session.captured_at, Session.created_at)
    rows = db.execute(
        select(Session.patient_id, func.min(when)).where(
            Session.tenant_id == tenant_id,
            Session.patient_id.isnot(None),
            Session.id.in_(_sessions_with_captures(tenant_id)),
        ).group_by(Session.patient_id)
    ).all()
    return {pid: _aware(first) for pid, first in rows if pid is not None and first is not None}


def _load_new_patient_days(db: DbSession, tenant_id: uuid.UUID, start: datetime, end: datetime) -> list[date]:
    rows = db.execute(
        select(Patient.created_at).where(
            Patient.tenant_id == tenant_id,
            Patient.status == PatientStatus.active,
            Patient.created_at >= start,
            Patient.created_at < end,
        )
    ).all()
    return [_aware(r[0]).date() for r in rows if r[0] is not None]


# --- Team -------------------------------------------------------------------------------------------
def _team_from_rows(members: list[dict[str, Any]], visits: list[VisitRow], captures: list[CaptureRow]) -> list[dict[str, Any]]:
    """Per-member productivity: visits (sessions they created) · distinct patients · captures, with a
    workload *share* (of visits) so the client draws the bars without re-summing."""
    by_user_visits: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)   # user → session ids
    by_user_patients: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    by_user_captures: dict[uuid.UUID, int] = defaultdict(int)
    for v in visits:
        by_user_visits[v.created_by_user_id].add(v.session_id)
        if v.patient_id is not None:
            by_user_patients[v.created_by_user_id].add(v.patient_id)
    for c in captures:
        by_user_captures[c.created_by_user_id] += 1
    total_visits = sum(len(s) for s in by_user_visits.values())
    out = []
    for m in members:
        uid = m["userId"]
        visit_n = len(by_user_visits.get(uid, ()))
        out.append({
            **m,
            "visits": visit_n,
            "patients": len(by_user_patients.get(uid, ())),
            "captures": by_user_captures.get(uid, 0),
            "share": round(visit_n / total_visits, 3) if total_visits else 0.0,
        })
    out.sort(key=lambda r: (r["patients"], r["visits"], r["captures"]), reverse=True)
    return out


def get_team(db: DbSession, principal: CurrentPrincipal, window: Window) -> dict[str, Any]:
    tenant_id = principal.tenant_id
    member_rows = db.execute(
        select(TenantMembership.user_id, TenantMembership.role, User.full_name, User.last_login_at)
        .join(User, User.id == TenantMembership.user_id)
        .where(TenantMembership.tenant_id == tenant_id, TenantMembership.status == MembershipStatus.active)
    ).all()
    # Last activity = most recent capture the user made in this tenant (fallback: last login).
    last_capture = dict(
        db.execute(
            select(Capture.created_by_user_id, func.max(Capture.created_at))
            .where(Capture.tenant_id == tenant_id, Capture.status != CaptureStatus.deleted)
            .group_by(Capture.created_by_user_id)
        ).all()
    )
    members = [
        {
            "userId": uid,
            "name": full_name,
            "role": role.value,
            "lastActiveAt": (_aware(last_capture.get(uid)) or _aware(last_login)).isoformat()
            if (last_capture.get(uid) or last_login)
            else None,
        }
        for uid, role, full_name, last_login in member_rows
    ]
    visits = _load_visits(db, tenant_id, window.start, window.end)
    captures = _load_captures(db, tenant_id, window.start, window.end)
    team = _team_from_rows(members, visits, captures)
    # userId → str for JSON.
    for row in team:
        row["userId"] = str(row["userId"])
    return {"range": window.range_key, "members": team}


# --- Patients ---------------------------------------------------------------------------------------
def _patients_from_rows(
    patients: list[dict[str, Any]], last_visit: dict[uuid.UUID, datetime], now: datetime
) -> dict[str, Any]:
    today = now.date()
    recency = {"active": 0, "lapsing": 0, "lapsed": 0, "neverVisited": 0}
    ages = {band: 0 for band in AGE_BANDS}
    ages_unknown = 0
    sexes = {"female": 0, "male": 0, "other": 0, "unknown": 0}
    for p in patients:
        bucket = recency_bucket(last_visit.get(p["id"]), now)
        recency[bucket if bucket else "neverVisited"] += 1
        band = age_band(p["dob"], today)
        if band is None:
            ages_unknown += 1
        else:
            ages[band] += 1
        sexes[normalize_sex(p["sex"])] += 1
    return {
        "recency": recency,
        "ageHistogram": [{"band": b, "count": ages[b]} for b in AGE_BANDS] + [{"band": "unknown", "count": ages_unknown}],
        "sexSplit": sexes,
    }


def _growth_series(patients: list[dict[str, Any]], window: Window) -> dict[str, Any]:
    """New patients per bucket in the window + the pre-window baseline, so the client draws a cumulative
    panel-growth line without loading the whole history."""
    keys = _bucket_sequence(window)
    buckets = {k: 0 for k in keys}
    baseline = 0
    for p in patients:
        created = _aware(p["createdAt"])
        if created is None:
            continue
        if created < window.start:
            baseline += 1
        elif created < window.end:
            buckets.setdefault(_bucket_start(created, window.granularity).isoformat(), 0)
            buckets[_bucket_start(created, window.granularity).isoformat()] += 1
    return {"baseline": baseline, "buckets": [{"date": k, "newPatients": buckets[k]} for k in sorted(buckets)]}


def get_patients(db: DbSession, principal: CurrentPrincipal, window: Window) -> dict[str, Any]:
    tenant_id = principal.tenant_id
    rows = db.execute(
        select(Patient.id, Patient.date_of_birth, Patient.sex, Patient.created_at).where(
            Patient.tenant_id == tenant_id, Patient.status == PatientStatus.active
        )
    ).all()
    patients = [{"id": pid, "dob": dob, "sex": sex, "createdAt": created} for pid, dob, sex, created in rows]
    last_visit = _last_visit_per_patient(db, tenant_id)
    now = _now()
    snapshot = _patients_from_rows(patients, last_visit, now)
    return {"range": window.range_key, "totalActive": len(patients), **snapshot, "growth": _growth_series(patients, window)}


# --- Treatments (Pro) -------------------------------------------------------------------------------
def require_treatments_capability(db: DbSession, tenant_id: uuid.UUID) -> None:
    if not tenant_has_capability(db, tenant_id, LIVE_REPORT_SYNTHESIS):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Treatment & product insights are a Pro capability.",
        )


def _administered_treatments(visits: Iterable[VisitRow]) -> Iterable[tuple[VisitRow, dict[str, Any]]]:
    """Yield real administrations (skip ``carriedForward`` 'same as last time' copies) — the same
    over-counting guard the lot ledger uses."""
    for v in visits:
        for t in v.treatments:
            if t.get("carriedForward") is True:
                continue
            yield v, t


def _ranked(counter: dict[str, int], limit: int = TOP_N) -> list[dict[str, Any]]:
    return [
        {"name": name, "count": count}
        for name, count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0].lower()))[:limit]
    ]


def _treatments_from_visits(visits: list[VisitRow], window: Window) -> dict[str, Any]:
    treatments_by_name: dict[str, int] = defaultdict(int)
    products: dict[str, int] = defaultdict(int)
    areas: dict[str, int] = defaultdict(int)
    consumption: dict[str, dict[str, Any]] = {}
    # Treatment mix over time: per bucket, count of each product (top products decided after the pass).
    mix_raw: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for v, t in _administered_treatments(visits):
        name = _treatment_name(t)
        brand = _treatment_brand(t)
        area = t.get("area")
        if name:
            treatments_by_name[name] += 1
            mix_raw[_bucket_start(v.when, window.granularity).isoformat()][name] += 1
        if brand:
            products[brand] += 1
        if isinstance(area, str) and area.strip():
            areas[area.strip()] += 1
        unit = normalize_unit(t.get("unit"))
        qty = t.get("quantity")
        if unit and isinstance(qty, (int, float)):
            entry = consumption.setdefault(unit, {"unit": unit, "total": 0.0, "count": 0})
            entry["total"] += float(qty)
            entry["count"] += 1

    top_products_for_mix = [row["name"] for row in _ranked(treatments_by_name, MIX_TOP_PRODUCTS)]
    keys = _bucket_sequence(window)
    mix_series = []
    for k in keys:
        row_counts = mix_raw.get(k, {})
        entry = {"date": k}
        other = 0
        for name, n in row_counts.items():
            if name in top_products_for_mix:
                entry[name] = n
            else:
                other += n
        if other:
            entry["other"] = other
        mix_series.append(entry)

    consumption_list = sorted(
        ({"unit": e["unit"], "total": round(e["total"], 2), "count": e["count"]} for e in consumption.values()),
        key=lambda e: -e["count"],
    )
    return {
        "topTreatments": _ranked(treatments_by_name),
        "topProducts": _ranked(products),
        "byArea": _ranked(areas),
        "consumption": consumption_list,
        "mixKeys": top_products_for_mix,
        "mixSeries": mix_series,
    }


def get_treatments(db: DbSession, principal: CurrentPrincipal, window: Window) -> dict[str, Any]:
    require_treatments_capability(db, principal.tenant_id)
    visits = _load_visits(db, principal.tenant_id, window.start, window.end)
    return {"range": window.range_key, **_treatments_from_visits(visits, window)}
