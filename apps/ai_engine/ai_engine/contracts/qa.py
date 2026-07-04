"""Patient Q&A contracts (AES-402): reply-draft cleaning + voice-edit revise/replace.

Both parsers return None on unusable output so the job can fall back (keep the deterministic draft /
leave the current draft unchanged). That fall-back trigger is the contract and is preserved here.
"""
from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict

QA_DRAFT_OUTPUT_VERSION = "2026-07-04.qa-draft-output.v1"
QA_REVISE_OUTPUT_VERSION = "2026-07-04.qa-revise-output.v1"

QA_REVISE_MODES = {"revise", "replace"}


class QaReviseOutput(BaseModel):
    """The voice-edit decision: revise the current draft vs replace it, plus the final reply text."""

    model_config = ConfigDict(extra="ignore")

    mode: str
    reply: str


def qa_revise_json_schema() -> dict[str, Any]:
    """Gateway ``json_schema`` for the Q&A voice-edit output (§3.2)."""
    return {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["revise", "replace"]},
            "reply": {"type": "string"},
        },
        "required": ["mode", "reply"],
    }


def parse_qa_draft_output(text: str) -> str | None:
    """Return a usable plain-text reply draft from the model output, else None to fall back."""
    if not text or not text.strip():
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) >= 2 else cleaned.strip("`")
        cleaned = cleaned.strip()
    return cleaned or None


def parse_qa_revise_output(text: str) -> dict[str, Any] | None:
    """Parse the strict JSON {mode, reply} from the model; None to fall back."""
    if not text or not text.strip():
        return None
    cleaned = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    reply = parsed.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        return None
    mode = parsed.get("mode") if parsed.get("mode") in QA_REVISE_MODES else "revise"
    return QaReviseOutput(mode=mode, reply=reply.strip()).model_dump()
