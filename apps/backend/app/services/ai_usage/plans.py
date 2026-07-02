"""Per-plan fair-use budget resolution.

A plan is derived from a tenant's ``(vertical, tier)`` (see capabilities.py): aesthetics-Basic carries
ZERO AI, so it has no usage limits at all; aesthetics-Pro and therapy carry the AI cost and are
metered. The monthly budget is framed per SEAT = effective revenue/seat × the AI-cost share, so it
recomputes when prices or the share change; the clinic budget is seats × budget/seat.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.config import settings
from app.models import MembershipRole, MembershipStatus, Tenant, TenantMembership
from app.services.capabilities import CAPTURE_AI_CAPABILITIES, capabilities

# Roles that consume an AI seat (a patient-surface membership is not a clinical seat).
_SEAT_ROLES = (MembershipRole.owner, MembershipRole.doctor, MembershipRole.assistant, MembershipRole.admin)


@dataclass(frozen=True)
class PlanBudget:
    """Resolved fair-use budget for a clinic in the current period."""

    plan: str  # "aes_basic" | "aes_pro" | "therapy"
    has_ai: bool
    seats: int
    budget_per_seat_usd: float
    budget_usd: float  # seats × per-seat (the clinic backstop)
    session_soft_cap_captures: int
    warn_threshold: float


def _plan_key(vertical: str | None, tier: str | None) -> str:
    normalized = (vertical or "").strip().lower()
    if normalized == "therapy":
        return "therapy"
    has_ai = bool(capabilities(vertical, tier) & CAPTURE_AI_CAPABILITIES)
    return "aes_pro" if has_ai else "aes_basic"


def active_seat_count(db: DbSession, tenant_id: uuid.UUID) -> int:
    """Count active clinical seats (memberships) for a clinic — the budget multiplier."""
    count = db.execute(
        select(func.count(TenantMembership.id)).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.status == MembershipStatus.active,
            TenantMembership.role.in_(_SEAT_ROLES),
        )
    ).scalar_one()
    return max(int(count or 0), 1)  # a clinic always has at least one seat


def budget_per_seat_usd() -> float:
    """Monthly AI budget per seat (USD). Dev/test override wins when set."""
    override = settings.ai_usage_test_budget_per_seat_usd
    if override and override > 0:
        return float(override)
    return float(settings.ai_budget_usd_per_seat)


def resolve_plan_budget(db: DbSession, tenant_id: uuid.UUID) -> PlanBudget:
    """Resolve the clinic's plan + monthly AI budget for the current period."""
    row = db.execute(select(Tenant.vertical, Tenant.tier).where(Tenant.id == tenant_id)).one_or_none()
    vertical, tier = (row[0], row[1]) if row is not None else (None, None)
    plan = _plan_key(vertical, tier)
    has_ai = plan != "aes_basic"
    if not has_ai:
        return PlanBudget(
            plan=plan, has_ai=False, seats=active_seat_count(db, tenant_id),
            budget_per_seat_usd=0.0, budget_usd=0.0, session_soft_cap_captures=0,
            warn_threshold=settings.ai_usage_warn_threshold,
        )
    seats = active_seat_count(db, tenant_id)
    per_seat = budget_per_seat_usd()
    soft_cap = (
        settings.ai_session_soft_cap_captures_therapy
        if plan == "therapy"
        else settings.ai_session_soft_cap_captures
    )
    return PlanBudget(
        plan=plan,
        has_ai=True,
        seats=seats,
        budget_per_seat_usd=per_seat,
        budget_usd=per_seat * seats,
        session_soft_cap_captures=int(soft_cap),
        warn_threshold=float(settings.ai_usage_warn_threshold),
    )
