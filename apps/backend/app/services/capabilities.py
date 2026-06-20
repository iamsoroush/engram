"""Capability resolution (P0.1).

Notari expresses product features as *capabilities*, not tiers. Each ``(vertical, tier)`` resolves to
a set of capabilities, and features gate on membership in that set — never on ``tier`` directly. This
keeps a vertical's tier composition in one place: aesthetics withholds the AI layer from Basic (a
deterministic Notes-killer) while therapy is a single plan that always includes it. See
``docs/spines.md`` §3.

Principle: **Basic = recall (deterministic), Pro = understanding (synthesis/matching)**. Tier
structure is per-vertical and follows where the value floor sits:

- aesthetics / dermatology — *organizational* floor → Basic (deterministic, no AI) + Pro (full set).
- therapy — *understanding* floor → a single plan = the full set (the AI itself is the value).

Structured capture, manual patient assignment, and search are the always-on deterministic floor and
need no capability flag; the capabilities below are the AI layer that sits on top of it.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import Tenant

# --- Capabilities (stable string identifiers; safe to persist in logs/metadata) ------------------
TRANSCRIPTION = "transcription"                  # audio → text
IMAGE_CAPTION = "image_caption"                  # AI photo captions
PATIENT_MATCHING = "patient_matching"            # AI auto match / create / reassign / suggest
OUT_OF_CONTEXT = "out_of_context"                # AI out-of-context detection
CROSS_VISIT_SYNTHESIS = "cross_visit_synthesis"  # AI patient memory (summary + history)
LIVE_REPORT_SYNTHESIS = "live_report_synthesis"  # synthesized/grouped live report (vs chronological)
POST_SESSION_QA = "post_session_qa"              # AI-drafted, doctor-verified patient Q&A (AES-402)

ALL_CAPABILITIES: frozenset[str] = frozenset(
    {
        TRANSCRIPTION,
        IMAGE_CAPTION,
        PATIENT_MATCHING,
        OUT_OF_CONTEXT,
        CROSS_VISIT_SYNTHESIS,
        LIVE_REPORT_SYNTHESIS,
        POST_SESSION_QA,
    }
)

# The deterministic floor: no AI capabilities (the aesthetics-Basic experience).
_NONE: frozenset[str] = frozenset()

_VALID_TIERS = {"basic", "pro"}


def capabilities(vertical: str | None, tier: str | None) -> frozenset[str]:
    """Resolve the AI capability set for a ``(vertical, tier)``.

    Gate features on membership in the returned set, not on ``tier``. The legacy ``clinic`` value and
    any unknown vertical behave like ``aesthetics`` (the current product); an unknown tier behaves
    like ``pro`` (the column default).
    """
    normalized_vertical = (vertical or "").strip().lower()
    resolved_tier = tier if tier in _VALID_TIERS else "pro"
    if normalized_vertical == "therapy":
        # Understanding floor → single plan; tier does not apply.
        return ALL_CAPABILITIES
    # aesthetics, dermatology, legacy clinic, and (until they get their own pipelines) radiology /
    # pathology: organizational floor → Basic = deterministic, Pro = full.
    return ALL_CAPABILITIES if resolved_tier == "pro" else _NONE


def tenant_capabilities(db: DbSession, tenant_id: uuid.UUID) -> frozenset[str]:
    """Resolve a tenant's capability set from its ``vertical`` + ``tier``."""
    row = db.execute(select(Tenant.vertical, Tenant.tier).where(Tenant.id == tenant_id)).one_or_none()
    if row is None:
        return capabilities(None, None)
    return capabilities(row[0], row[1])


def tenant_has_capability(db: DbSession, tenant_id: uuid.UUID, capability: str) -> bool:
    """True when the tenant's resolved capability set includes ``capability``."""
    return capability in tenant_capabilities(db, tenant_id)


# The AI capabilities exercised by the per-capture processing job (transcription, photo captioning,
# matching, out-of-context). A tenant with none of these — e.g. aesthetics-Basic — skips the capture
# AI pipeline entirely: the capture is saved deterministically, with no AI job and no `processing`
# state (AES-101). Notes carry no AI capability of their own — they are a pure passthrough — but a Pro
# tenant still processes them via the other capabilities below.
CAPTURE_AI_CAPABILITIES: frozenset[str] = frozenset(
    {TRANSCRIPTION, IMAGE_CAPTION, PATIENT_MATCHING, OUT_OF_CONTEXT}
)


def tenant_processes_captures_with_ai(db: DbSession, tenant_id: uuid.UUID) -> bool:
    """True if a capture upload should dispatch the AI processing job for this tenant.

    False for the zero-AI Basic lifecycle (no capture-AI capabilities) — the capture is saved
    deterministically with no AI job and no ``processing`` state.
    """
    return bool(tenant_capabilities(db, tenant_id) & CAPTURE_AI_CAPABILITIES)
