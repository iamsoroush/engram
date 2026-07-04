"""Worklist routes: a clinician's "today / up next" soft queue (AES-903).

A self-contained router mounted by ``main.py``. Handlers stay thin — logic lives in
``app/services/worklist``.
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentPrincipal, staff_or_admin_required, staff_required
from app.db.session import get_db
from app.schemas.api import WorklistEntryCreate, WorklistEntryResolve
from app.services.worklist import create_worklist_entry, list_worklist, resolve_worklist_entry

worklist_api = APIRouter(prefix="/api/v1")


@worklist_api.get("/worklist")
def list_worklist_route(
    scope: str = Query(default="mine", pattern="^(mine|clinic)$"),
    status: str = Query(default="waiting", pattern="^(waiting|seen|cancelled|all)$"),
    clinician_id: str | None = Query(default=None, alias="clinicianId"),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """A clinician's "Today / up next" worklist (AES-903). Default: the caller's waiting entries."""
    return list_worklist(db, principal, scope=scope, status_filter=status, clinician_id=clinician_id)


@worklist_api.post("/worklist")
def create_worklist_route(
    request: WorklistEntryCreate,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Line a patient up for a clinician (AES-903). A soft lane — capture-first is never blocked."""
    return create_worklist_entry(
        db,
        principal,
        patient_id=request.patient_id,
        clinician_user_id=request.clinician_user_id,
        note=request.note,
    )


@worklist_api.post("/worklist/{entry_id}/seen")
def worklist_entry_seen_route(
    entry_id: str,
    request: WorklistEntryResolve | None = None,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Clear a worklist entry as seen, optionally linking the session the clinician started."""
    body = request or WorklistEntryResolve()
    return resolve_worklist_entry(db, principal, entry_id, new_status="seen", session_id=body.session_id)


@worklist_api.delete("/worklist/{entry_id}")
def cancel_worklist_entry_route(
    entry_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Cancel (remove) a worklist entry that no longer applies."""
    return resolve_worklist_entry(db, principal, entry_id, new_status="cancelled")
