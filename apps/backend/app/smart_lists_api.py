"""Smart lists + lot/product recall routes (Pro; AES-501 / AES-502).

A self-contained router so the feature stays in mostly-new files: ``main.py`` only mounts it. All
endpoints are read-only, Pro-gated on ``live_report_synthesis`` (in the service), and tenant-scoped.
Logic lives in ``app/services/smart_lists.py``; these handlers stay thin. See
``docs/ux/screens/patients.md`` (Lists tab).
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentPrincipal, staff_or_admin_required
from app.db.session import get_db
from app.services import smart_lists

smart_lists_api = APIRouter(prefix="/api/v1", tags=["smart-lists"])


@smart_lists_api.get("/smart-lists")
def smart_lists_counts(
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Live counts for the smart-list rail (AES-501): seen-this-week · due-to-return · missing-after-photo."""
    return smart_lists.smart_list_counts(db, principal)


@smart_lists_api.get("/smart-lists/{key}")
def smart_list_rows(
    key: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """The rows of one smart list (paginated). 404 for an unknown key."""
    return smart_lists.smart_list_rows(db, principal, key, limit=limit, offset=offset)


@smart_lists_api.get("/lot-ledger")
def lot_ledger(
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Distinct lots + products in the clinic's extracted data with counts (AES-502 browse/suggest)."""
    return smart_lists.lot_ledger(db, principal)


@smart_lists_api.get("/lot-recall")
def lot_recall(
    lot: str | None = Query(default=None),
    product: str | None = Query(default=None),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Every patient/visit that received a given lot (exact) or product (AES-502 recall cohort)."""
    return smart_lists.lot_recall(db, principal, lot=lot, product=product)
