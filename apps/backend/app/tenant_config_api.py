"""Tenant/clinic configuration routes: AI usage, AI model selection, language settings, plan.

A self-contained router mounted by ``main.py``. Handlers stay thin — logic lives in
``app/services/ai_usage``, ``app/services/ai_model_config``, and ``app/auth/service``.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentPrincipal, get_current_principal, staff_or_admin_required, tenant_admin_required
from app.auth.service import set_tenant_plan, update_tenant_settings
from app.config import settings
from app.db.session import get_db
from app.schemas.tenant import AiModelConfigUpdate, AiUsageDevSetRequest
from app.schemas.auth import PlanUpdateRequest, TenantSettingsUpdate
from app.services.ai_model_config import ai_model_settings_payload, set_ai_model_overrides

tenant_config_api = APIRouter(prefix="/api/v1")


@tenant_config_api.get("/ai-usage")
def get_ai_usage_route(
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Any:
    """Return the clinic's current-period fair-use AI usage state (for the usage/limit UI)."""
    from app.services.ai_usage import clinic_usage_state_dict

    return clinic_usage_state_dict(db, principal.tenant_id)


@tenant_config_api.post("/ai-usage/dev/set")
def set_ai_usage_dev_route(
    request: AiUsageDevSetRequest,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> Any:
    """DEV/TEST ONLY: jump the clinic to a target % of its monthly AI budget (fast path to limit states).

    Guarded to dev auth mode so it can never move real spend in production.
    """
    if settings.auth_mode != "dev":
        raise HTTPException(status_code=404, detail="Not found")
    from app.services.ai_usage import set_dev_usage_percent

    return set_dev_usage_percent(db, principal.tenant_id, request.percent)


@tenant_config_api.patch("/tenant/settings")
def update_tenant_settings_route(
    request: TenantSettingsUpdate,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> Any:
    """Update tenant language preferences (transcription / report)."""
    return update_tenant_settings(db, principal, provided=request.model_dump(exclude_unset=True))


@tenant_config_api.get("/ai-config/models")
def get_ai_models_route(
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> Any:
    """Return the live per-task AI model selection (blank model = worker env default)."""
    return ai_model_settings_payload(db)


@tenant_config_api.put("/ai-config/models")
def update_ai_models_route(
    request: AiModelConfigUpdate,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> Any:
    """Set per-task AI model overrides. Takes effect on the next AI request (no restart)."""
    set_ai_model_overrides(db, request.models, user_id=principal.user_id)
    return ai_model_settings_payload(db)


@tenant_config_api.patch("/clinic/plan")
def clinic_plan_route(
    request: PlanUpdateRequest,
    principal: CurrentPrincipal = Depends(tenant_admin_required),
    db: Session = Depends(get_db),
) -> Any:
    """Switch the clinic plan/tier (basic | pro) — owner/admin, no payment. Returns the tenant profile."""
    return set_tenant_plan(db, principal, tier=request.tier)
