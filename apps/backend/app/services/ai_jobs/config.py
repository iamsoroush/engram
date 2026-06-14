"""Tenant-scoped configuration getters and the report-template loader."""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import Tenant
from app.services.reporting import report_template_payload

__all__ = [
    "tenant_tier",
    "tenant_transcription_language",
    "tenant_report_language",
    "tenant_match_strictness",
    "load_report_template",
]


def tenant_tier(db: DbSession, tenant_id: uuid.UUID) -> str:
    """Return a tenant's intelligence tier ('basic'|'pro'); AI auto-assignment is Pro-only."""
    tier = db.execute(select(Tenant.tier).where(Tenant.id == tenant_id)).scalar_one_or_none()
    return tier if tier in {"basic", "pro"} else "pro"


def tenant_transcription_language(db: DbSession, tenant_id: uuid.UUID) -> str:
    """Return the tenant's preferred transcription language ('auto' | a BCP-47-ish code).

    'auto' = transcribe verbatim in the spoken language/script; a specific code asks the model
    to transcribe in that language (improves accuracy/matching for known-language clinics).
    """
    value = db.execute(select(Tenant.transcription_language).where(Tenant.id == tenant_id)).scalar_one_or_none()
    return value.strip() if isinstance(value, str) and value.strip() else "auto"


def tenant_report_language(db: DbSession, tenant_id: uuid.UUID) -> str | None:
    """Return the tenant's preferred report language, or None to follow the template default."""
    value = db.execute(select(Tenant.report_language).where(Tenant.id == tenant_id)).scalar_one_or_none()
    return value.strip() if isinstance(value, str) and value.strip() else None


def tenant_match_strictness(db: DbSession, tenant_id: uuid.UUID) -> str:
    """Return the tenant's fuzzy-match auto-apply strictness ('strict'|'balanced'|'lenient')."""
    value = db.execute(select(Tenant.match_strictness).where(Tenant.id == tenant_id)).scalar_one_or_none()
    return value if value in {"strict", "balanced", "lenient"} else "strict"


def load_report_template(template_key: str | None) -> dict[str, str]:
    """Load the centralized report template by stable key."""
    try:
        return report_template_payload(template_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported report template") from exc
