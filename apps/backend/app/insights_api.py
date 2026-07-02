"""Clinic insights routes (owner/admin analytics).

A self-contained router mounted by ``main.py``. Handlers stay thin; all aggregation lives in
``app/services/insights.py``. Every endpoint is read-only, tenant-scoped, and **owner/admin-gated**
(``tenant_admin_required``); ``/insights/treatments`` is additionally Pro-gated in the service. See
``docs/ux/screens/insights.md``.
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentPrincipal, tenant_admin_required
from app.db.session import get_db
from app.services import insights

insights_api = APIRouter(prefix="/api/v1/insights", tags=["insights"])


def _window(range: str, frm: str | None, to: str | None) -> insights.Window:
    return insights.resolve_window(range, now=insights._now(), frm=frm, to=to)


@insights_api.get("/overview")
def overview(
    range: str = Query(default="this-month"),
    frm: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    principal: CurrentPrincipal = Depends(tenant_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Clinic pulse: KPIs (+ prior-period deltas), activity series, new/returning, busy-time heatmap, backlog."""
    return insights.get_overview(db, principal, _window(range, frm, to))


@insights_api.get("/team")
def team(
    range: str = Query(default="this-month"),
    frm: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    principal: CurrentPrincipal = Depends(tenant_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Per-member productivity (visits · patients · captures · last active) + workload share."""
    return insights.get_team(db, principal, _window(range, frm, to))


@insights_api.get("/patients")
def patients(
    range: str = Query(default="this-month"),
    frm: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    principal: CurrentPrincipal = Depends(tenant_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Patient panel: recency cohorts, age histogram, sex split, cumulative growth."""
    return insights.get_patients(db, principal, _window(range, frm, to))


@insights_api.get("/treatments")
def treatments(
    range: str = Query(default="this-month"),
    frm: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    principal: CurrentPrincipal = Depends(tenant_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Pro: top treatments, consumption-by-unit, top products, treatment-mix series, by-area (403 on Basic)."""
    return insights.get_treatments(db, principal, _window(range, frm, to))
