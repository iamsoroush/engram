"""Patient-share routes: tenant-side share management + the public read-only share surface.

A self-contained router mounted by ``main.py``. Handlers stay thin — logic lives in
``app/services/patient_surface``. The public ``/share/*`` routes are unauthenticated (token-scoped
in the service); the media plumbing lives in ``app/http``.
"""

from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentPrincipal, staff_or_admin_required, staff_required
from app.db.session import get_db
from app.http.responses import ranged_file_response
from app.schemas.api import PatientShareCreate
from app.services.patient_surface import (
    create_patient_share,
    get_patient_share_payload,
    list_patient_shares,
    public_share_media,
    public_share_payload,
    revoke_patient_share,
)
from app.storage import ObjectStore, get_object_store

shares_api = APIRouter(prefix="/api/v1")


@shares_api.post("/patient-shares")
def patient_shares_create_route(
    request: PatientShareCreate,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a tokenized, revocable share of curated content (AES-303/304/403)."""
    return create_patient_share(db, principal, request)


@shares_api.get("/patient-shares")
def patient_shares_list_route(
    patient_id: str | None = Query(default=None, alias="patientId"),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List the tenant's patient shares, optionally scoped to one patient."""
    return list_patient_shares(db, principal, patient_id=patient_id)


@shares_api.get("/patient-shares/{share_id}")
def patient_shares_get_route(
    share_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one share with its curated preview (AES-403 per-share preview)."""
    return get_patient_share_payload(db, principal, share_id)


@shares_api.post("/patient-shares/{share_id}/revoke")
def patient_shares_revoke_route(
    share_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Revoke a share so its public link stops working (AES-403)."""
    return revoke_patient_share(db, principal, share_id)


@shares_api.get("/share/{token}")
def public_share_route(token: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """PUBLIC, read-only: the patient's curated report + aftercare for a share token (AES-401)."""
    return public_share_payload(db, token)


@shares_api.get("/share/{token}/media/{capture_id}")
def public_share_media_route(
    token: str,
    capture_id: str,
    range_header: str | None = Header(default=None, alias="Range"),
    db: Session = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store),
) -> Response:
    """PUBLIC, read-only: stream a curated photo for a share (only if it is in the share)."""
    media = public_share_media(db, object_store=object_store, token=token, capture_id=capture_id)
    return ranged_file_response(
        content=media["content"],
        media_type=media["media_type"],
        filename=media["filename"],
        range_header=range_header,
    )
