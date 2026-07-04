"""Cross-visit safety-reconcile contract: one keys-only decision per candidate flag.

Selection-only and safety-first: an unknown key is dropped; a duplicate/superseded whose ofKey isn't a
real OTHER candidate downgrades to 'keep' (never silently lose a distinct flag). That guard is the
contract and is preserved here.
"""
from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict

SAFETY_RECONCILE_OUTPUT_VERSION = "2026-07-04.safety-reconcile.v1"

RECONCILE_STATUSES = {"keep", "duplicate", "superseded"}


class ReconcileDecision(BaseModel):
    """One flag's verdict: keep it, or collapse/supersede it onto another flag's key."""

    model_config = ConfigDict(extra="ignore")

    status: str
    ofKey: str | None = None


def parse_safety_reconcile_output(raw_text: str, *, candidate_keys: list[str]) -> dict[str, dict[str, Any]] | None:
    """Validate the reconcile output into ``{key: {status, ofKey}}``, or None to fall back to the union.

    Safety-first: an unknown key is dropped; a duplicate/superseded whose ofKey isn't a real candidate is
    downgraded to 'keep'; any candidate with no decision defaults to 'keep' upstream.
    """
    if not raw_text or not raw_text.strip():
        return None
    text = raw_text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("decisions"), list):
        return None
    keys = set(candidate_keys)
    decisions: dict[str, dict[str, Any]] = {}
    for item in parsed["decisions"]:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        status = item.get("status")
        if key not in keys or status not in RECONCILE_STATUSES:
            continue
        of_key = item.get("ofKey")
        # A collapse/supersede must point at a real OTHER candidate; otherwise keep (never drop).
        if status in {"duplicate", "superseded"} and (of_key not in keys or of_key == key):
            status, of_key = "keep", None
        decisions[key] = ReconcileDecision(status=status, ofKey=of_key if status != "keep" else None).model_dump()
    return decisions
