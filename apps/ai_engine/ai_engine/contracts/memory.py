"""Patient-memory contract (Pro): longitudinal summary + history card.

The model returns None when its output is unusable so the job can fall back to the backend-provided
deterministic content — that fall-back trigger (summary/history/snapshot/non-empty-sections required,
card optional) is the contract and is preserved here.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict

PATIENT_MEMORY_OUTPUT_VERSION = "2026-07-04.patient-memory-output.v1"


class PatientMemoryOutput(BaseModel):
    """Validated patient-memory output: card summary + history + optional line-up card."""

    model_config = ConfigDict(extra="ignore")

    summary: str
    history: dict[str, Any]
    card: dict[str, Any] | None = None


def parse_patient_memory_output(text: str) -> dict[str, Any] | None:
    """Parse the model's patient-memory JSON; return None if unusable so the caller can fall back."""
    if not text or not text.strip():
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) >= 2 else cleaned.strip("`")
        if cleaned.lstrip().lower().startswith("json"):
            cleaned = cleaned.lstrip()[4:]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    summary = data.get("summary")
    history = data.get("history")
    if not isinstance(summary, str) or not summary.strip() or not isinstance(history, dict):
        return None
    if not isinstance(history.get("snapshot"), str):
        return None
    sections = history.get("sections")
    if not isinstance(sections, list) or not sections:
        return None
    # The compact line-up card is optional (backend layers in a deterministic fallback if absent).
    card = data.get("card")
    return PatientMemoryOutput(
        summary=summary.strip(), history=history, card=card if isinstance(card, dict) else None
    ).model_dump()
