"""Attention roll-up route (Close-the-day / AES-1001).

A thin, self-contained router mounted by ``main.py``. The roll-up itself lives in
``app/services/attention``; this handler only parses the query and delegates.
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentPrincipal, staff_or_admin_required
from app.db.session import get_db
from app.schemas.attention import AttentionResponse
from app.services.attention import build_attention_feed

attention_api = APIRouter(prefix="/api/v1")


@attention_api.get("/attention", response_model=AttentionResponse)
def attention_feed_route(
    scope: str = Query(default="mine", pattern="^(mine|clinic)$"),
    tz_offset_minutes: int = Query(default=0, alias="tzOffsetMinutes", ge=-840, le=840),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Unified severity-tiered attention feed + aggregate counts for the sweep and the indicator."""
    return build_attention_feed(
        db,
        principal,
        scope=scope,
        tz_offset_minutes=tz_offset_minutes,
    )
