"""Author attribution (E9, AES-901).

Every capture / visit / note shows **who created it** — deterministic, from ``created_by_user_id``
(no AI). A capture's author is the seat that captured it; a session's author is its owner. The
display name resolves to ``full_name`` (falling back to ``email``).

``db.get(User, id)`` is served from SQLAlchemy's per-session identity map, so resolving the same
author repeatedly (e.g. every capture in one visit) costs at most one query per distinct user.
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session as DbSession

from app.models import User


def attribution_payload(db: DbSession | None, user_id: uuid.UUID | str | None) -> dict[str, Any] | None:
    """``{"userId", "displayName"}`` for an author, or ``None`` when unknown.

    ``displayName`` is ``None`` (not omitted) when the user can't be resolved, so the client can
    still show "by <unknown> · time" without a missing-field crash.
    """
    if user_id is None:
        return None
    user = db.get(User, user_id) if db is not None else None
    return {
        "userId": str(user_id),
        "displayName": (user.full_name or user.email) if user is not None else None,
    }
