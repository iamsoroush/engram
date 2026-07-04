"""AI-quality feedback routes — the thin endpoint behind the eval golden-set harvester (eval-epic §1b).

A self-contained router so the feature stays in mostly-new files: ``main.py`` only mounts it. Staff
corrections of AI outputs (transcript/caption/treatment/patient-match) are harvested *server-side* in
the correction services (``services.feedback.record_*``); this router carries the lightweight
report/brief thumbs rating (and any other client signal) plus a tenant-scoped read for the harvester /
QA. Handlers stay thin — all logic lives in ``app/services/feedback.py``.
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentPrincipal, staff_or_admin_required, staff_required
from app.db.session import get_db
from app.schemas.feedback import FeedbackCreate
from app.services import feedback

feedback_api = APIRouter(prefix="/api/v1", tags=["feedback"])


@feedback_api.post("/feedback")
def create_feedback_route(
    request: FeedbackCreate,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Record a client-supplied AI-quality signal (the report/brief thumbs rating)."""
    return feedback.create_feedback(db, principal, request)


@feedback_api.get("/feedback")
def list_feedback_route(
    limit: int = Query(default=50, ge=1, le=200),
    kind: str | None = Query(default=None),
    ai_output_type: str | None = Query(default=None, alias="aiOutputType"),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List recent harvested feedback for the tenant (newest first) — the eval-harvest / QA read."""
    return feedback.list_feedback(db, principal, limit=limit, kind=kind, ai_output_type=ai_output_type)
