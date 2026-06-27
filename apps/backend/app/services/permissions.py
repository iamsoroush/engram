"""Multi-seat role permissions (E9, AES-905/902/906).

Aesthetics is a *shared workspace*: any provider can work with any patient. But a session is
**owned** by whoever created it (capture-first → the capturer owns), and editing/curating it is the
owner's by default. What every *other* (non-owner) role may do is **tenant-configurable and
permissive by default** — a few presets, not a granular matrix. See
``docs/ux/redesign-foundation.md`` §7.

Three ordered presets, each a superset of the one below:

- ``contribute`` — append captures to anyone's session. The floor: contributing never blocks, so
  this is the minimum for every staff role and is what capture-first relies on.
- ``reassign`` — contribute **+** change which patient an already-assigned visit belongs to.
- ``full`` — reassign **+** edit/curate the session (title, summary, report, status).

The **session owner is always ``full`` on their own session**, and **admins are always ``full``**
everywhere (they manage the clinic) — neither is stored in ``tenant.role_permissions``. Only the
non-owner clinical roles (``doctor`` peers, ``assistant``) carry a configurable preset.

Permissive zero-config default (foundation §7: *contribute open · reassign = receptionist + owner ·
edit = owner*). This codebase's staff roles are ``doctor``/``assistant`` (no separate receptionist),
so the receptionist's reassign capability maps onto ``assistant`` — the intake/support role here:

- ``assistant`` → ``reassign`` (can file/reassign, like a receptionist; cannot edit others' records)
- ``doctor`` (a non-owner peer) → ``contribute`` (collaborate on a colleague's visit, but edit/
  reassign stays with the owner unless an admin loosens it)

Both are loosenable ("assistant: full") or tightenable ("assistant: contribute") in Settings.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import MembershipStatus, Session, Tenant, TenantMembership

CONTRIBUTE = "contribute"
REASSIGN = "reassign"
FULL = "full"

# Ordered low → high; a higher rank includes everything below it.
PRESET_RANK: dict[str, int] = {CONTRIBUTE: 0, REASSIGN: 1, FULL: 2}
VALID_PRESETS: frozenset[str] = frozenset(PRESET_RANK)

# Roles that admins may configure a preset for (non-owner clinical roles). ``admin`` is always full;
# ``patient`` never reaches staff surfaces.
CONFIGURABLE_ROLES: tuple[str, ...] = ("doctor", "assistant")

# Permissive zero-config default (foundation §7).
DEFAULT_ROLE_PERMISSIONS: dict[str, str] = {"doctor": CONTRIBUTE, "assistant": REASSIGN}


def resolve_role_permissions(stored: dict | None) -> dict[str, str]:
    """Merge a tenant's stored overrides over the permissive defaults.

    Only known roles + valid presets survive; anything else falls back to the default so a bad
    stored value can never silently *expand* access.
    """
    resolved = dict(DEFAULT_ROLE_PERMISSIONS)
    if isinstance(stored, dict):
        for role in CONFIGURABLE_ROLES:
            value = stored.get(role)
            if isinstance(value, str) and value in VALID_PRESETS:
                resolved[role] = value
    return resolved


def tenant_role_permissions(db: DbSession, tenant_id: uuid.UUID) -> dict[str, str]:
    """The tenant's effective per-role presets (defaults merged with stored overrides)."""
    stored = db.execute(select(Tenant.role_permissions).where(Tenant.id == tenant_id)).scalar_one_or_none()
    return resolve_role_permissions(stored)


def role_permission_level(roles: frozenset[str] | set[str], role_permissions: dict[str, str]) -> str:
    """The highest preset a set of roles grants (admin → full; otherwise the max configured preset).

    A non-owner with no recognized staff role still gets the ``contribute`` floor (append never
    blocks). Ownership is handled by the callers below, not here.
    """
    # ``owner`` (clinic founder) and ``admin`` are always full everywhere — neither carries a
    # configurable per-role preset.
    if roles & {"owner", "admin"}:
        return FULL
    level = CONTRIBUTE
    for role in roles:
        preset = role_permissions.get(role)
        if preset is not None and PRESET_RANK[preset] > PRESET_RANK[level]:
            level = preset
    return level


def roles_for_user_in_tenant(db: DbSession, tenant_id: uuid.UUID, user_id: uuid.UUID | None) -> frozenset[str]:
    """Active membership roles for a user in a tenant (used to grade a capture's author)."""
    if user_id is None:
        return frozenset()
    rows = db.execute(
        select(TenantMembership.role).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user_id,
            TenantMembership.status == MembershipStatus.active,
        )
    ).scalars()
    return frozenset(role.value for role in rows)


def session_permission_for_roles(*, is_owner: bool, roles: frozenset[str] | set[str], role_permissions: dict[str, str]) -> str:
    """Effective preset for a viewer on a session: owner → full, else by role."""
    if is_owner:
        return FULL
    return role_permission_level(roles, role_permissions)


def can_reassign(level: str) -> bool:
    return PRESET_RANK.get(level, 0) >= PRESET_RANK[REASSIGN]


def can_edit(level: str) -> bool:
    return PRESET_RANK.get(level, 0) >= PRESET_RANK[FULL]


def user_session_permission(db: DbSession, *, session: Session, user_id: uuid.UUID) -> str:
    """Resolve a user's effective preset on a specific session (owner-aware, policy-aware)."""
    if session.created_by_user_id == user_id:
        return FULL
    roles = roles_for_user_in_tenant(db, session.tenant_id, user_id)
    return role_permission_level(roles, tenant_role_permissions(db, session.tenant_id))


def user_can_reassign_session(db: DbSession, *, session: Session, user_id: uuid.UUID | None) -> bool:
    """Whether ``user_id`` is permitted to reassign ``session`` to a different patient.

    The AES-906 gate for AI intent: the capture's author may auto-apply a reassignment only if their
    role permits it; otherwise it becomes a suggestion to the owner (never a block).
    """
    if user_id is None:
        return False
    return can_reassign(user_session_permission(db, session=session, user_id=user_id))
