"""Aftercare templates CRUD (aesthetics-Basic, AES-702).

Per-procedure, deterministic aftercare instruction templates managed in Settings (AES-702) and
attached — selectable + editable per send — to a curated patient share (AES-304). Zero AI.
"""

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.auth.service import audit
from app.models import AftercareTemplate
from app.schemas.aftercare import AftercareTemplatePatch, AftercareTemplateWrite


def _normalize_procedure_type(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().lower()
    return cleaned or None


def aftercare_template_payload(template: AftercareTemplate) -> dict[str, Any]:
    """Serialize an aftercare template for the API."""
    return {
        "id": str(template.id),
        "tenantId": str(template.tenant_id),
        "name": template.name,
        "procedureType": template.procedure_type,
        "body": template.body,
        "isActive": template.is_active,
        "createdAt": template.created_at.isoformat() if template.created_at else None,
        "updatedAt": template.updated_at.isoformat() if template.updated_at else None,
    }


def get_aftercare_template(db: DbSession, tenant_id: uuid.UUID, template_id: str) -> AftercareTemplate:
    """Load a tenant's aftercare template or raise 404."""
    try:
        parsed = uuid.UUID(template_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid template_id") from exc
    template = db.execute(
        select(AftercareTemplate).where(
            AftercareTemplate.id == parsed,
            AftercareTemplate.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aftercare template not found")
    return template


def list_aftercare_templates(
    db: DbSession,
    principal: CurrentPrincipal,
    *,
    procedure_type: str | None = None,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    """List the tenant's aftercare templates, newest first."""
    statement = select(AftercareTemplate).where(AftercareTemplate.tenant_id == principal.tenant_id)
    if (normalized := _normalize_procedure_type(procedure_type)) is not None:
        statement = statement.where(AftercareTemplate.procedure_type == normalized)
    if not include_inactive:
        statement = statement.where(AftercareTemplate.is_active.is_(True))
    templates = db.execute(statement.order_by(AftercareTemplate.updated_at.desc())).scalars()
    return [aftercare_template_payload(template) for template in templates]


def create_aftercare_template(db: DbSession, principal: CurrentPrincipal, request: AftercareTemplateWrite) -> dict[str, Any]:
    """Create an aftercare template."""
    template = AftercareTemplate(
        tenant_id=principal.tenant_id,
        name=request.name.strip(),
        procedure_type=_normalize_procedure_type(request.procedure_type),
        body=request.body,
        is_active=request.is_active,
        created_by_user_id=principal.user_id,
    )
    db.add(template)
    db.flush()
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="aftercare_template.create",
        target_type="aftercare_template",
        target_id=template.id,
        details={"name": template.name, "procedure_type": template.procedure_type},
    )
    db.commit()
    db.refresh(template)
    return aftercare_template_payload(template)


def update_aftercare_template(
    db: DbSession,
    principal: CurrentPrincipal,
    template_id: str,
    request: AftercareTemplatePatch,
) -> dict[str, Any]:
    """Patch editable fields of an aftercare template (only the keys provided)."""
    template = get_aftercare_template(db, principal.tenant_id, template_id)
    updates = request.model_dump(exclude_unset=True)
    if "name" in updates and request.name is not None:
        template.name = request.name.strip()
    if "procedure_type" in updates:
        template.procedure_type = _normalize_procedure_type(request.procedure_type)
    if "body" in updates and request.body is not None:
        template.body = request.body
    if "is_active" in updates and request.is_active is not None:
        template.is_active = request.is_active
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="aftercare_template.update",
        target_type="aftercare_template",
        target_id=template.id,
        details={"fields": sorted(updates.keys())},
    )
    db.commit()
    db.refresh(template)
    return aftercare_template_payload(template)


def delete_aftercare_template(db: DbSession, principal: CurrentPrincipal, template_id: str) -> dict[str, Any]:
    """Delete an aftercare template."""
    template = get_aftercare_template(db, principal.tenant_id, template_id)
    deleted_id = str(template.id)
    db.delete(template)
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="aftercare_template.delete",
        target_type="aftercare_template",
        target_id=template.id,
        details={},
    )
    db.commit()
    return {"id": deleted_id, "status": "deleted"}
