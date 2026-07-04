"""Photo-caption contract: a neutral image→text description plus optional pairing/OOC attributes.

The caption is an OBJECTIVE stand-in for the image (never a diagnosis). A gateway that returns a bare
caption string (no JSON) still degrades to a usable caption with no attributes — that back-compat is
part of the contract and is preserved here.
"""
from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ai_engine.core.text import normalize_digits_to_latin
from ai_engine.core.util import clamp_confidence

CAPTION_OUTPUT_VERSION = "2026-07-04.caption-output.v1"

PAIRING_LATERALITIES = {"left", "right", "bilateral", "midline", "central"}
PAIRING_PHASES = {"before", "after", "during", "intraop", "other"}


class PairingAttributes(BaseModel):
    """Deterministic before/after pairing attributes the backend consumes to build photo pairs."""

    model_config = ConfigDict(extra="ignore")

    region: str | None = None
    laterality: str | None = None
    view: str | None = None
    phase: str | None = None
    isProductLabel: bool = False


class CaptionResult(BaseModel):
    """A structured caption: clean ``caption`` text (consumed by AI jobs) + UI ``display`` + attributes."""

    model_config = ConfigDict(extra="ignore")

    caption: str
    display: str
    confidence: float | None = None
    outOfContext: dict[str, Any] | None = None
    pairing: dict[str, Any]
    uncertainties: list[str] = Field(default_factory=list)


def normalize_caption_pairing(raw: Any) -> dict[str, Any]:
    """Coerce model pairing output into the stable {region,laterality,view,phase,isProductLabel} shape."""
    pairing = raw if isinstance(raw, dict) else {}

    def _text(value: Any) -> str | None:
        return value.strip().lower() if isinstance(value, str) and value.strip() else None

    laterality = _text(pairing.get("laterality"))
    phase = _text(pairing.get("phase"))
    return PairingAttributes(
        region=pairing.get("region").strip() if isinstance(pairing.get("region"), str) and pairing.get("region").strip() else None,
        laterality=laterality if laterality in PAIRING_LATERALITIES else None,
        view=pairing.get("view").strip() if isinstance(pairing.get("view"), str) and pairing.get("view").strip() else None,
        phase=phase if phase in PAIRING_PHASES else None,
        isProductLabel=pairing.get("isProductLabel") is True,
    ).model_dump()


def _caption_display_text(raw_display: Any, caption_text: str) -> str:
    """Return the model's Markdown display variant only when it is the SAME text with just **bold**
    added (verified by stripping the markers); else fall back to the clean caption. Digits normalized."""
    if not isinstance(raw_display, str) or not raw_display.strip():
        return caption_text
    candidate = normalize_digits_to_latin(raw_display.strip())

    def _plain(value: str) -> str:
        return re.sub(r"\s+", " ", value.replace("**", "")).strip().lower()

    return candidate if _plain(candidate) == _plain(caption_text) else caption_text


def parse_caption_output(raw_text: str) -> dict[str, Any] | None:
    """Parse the structured caption JSON; degrade to a plain-text caption when it isn't JSON.

    Returns ``{caption, display, confidence, outOfContext, pairing, uncertainties}`` or None when there
    is no usable caption text. A gateway that returns a bare caption string still works.
    """
    text = raw_text.strip()
    if not text:
        return None
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    parsed: Any = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if not isinstance(parsed, dict):
        # Not JSON — treat the whole response as a plain caption (back-compatible, no attributes).
        plain = normalize_digits_to_latin(raw_text.strip())
        return CaptionResult(
            caption=plain, display=plain, confidence=None, outOfContext=None,
            pairing=normalize_caption_pairing(None), uncertainties=[],
        ).model_dump()
    caption = parsed.get("caption")
    if not isinstance(caption, str) or not caption.strip():
        return None
    ooc_raw = parsed.get("outOfContext")
    out_of_context = None
    if isinstance(ooc_raw, dict) and ooc_raw.get("present") is True:
        reason = ooc_raw.get("reason")
        out_of_context = {
            "present": True,
            "confidence": clamp_confidence(ooc_raw.get("confidence")),
            "reason": str(reason).strip() if isinstance(reason, str) and reason.strip() else None,
        }
    confidence = parsed.get("confidence")
    uncertainties = parsed.get("uncertainties")
    caption_text = normalize_digits_to_latin(caption.strip())
    return CaptionResult(
        caption=caption_text,
        display=_caption_display_text(parsed.get("display"), caption_text),
        confidence=clamp_confidence(confidence) if isinstance(confidence, int | float) and not isinstance(confidence, bool) else None,
        outOfContext=out_of_context,
        pairing=normalize_caption_pairing(parsed.get("pairing")),
        uncertainties=[str(value).strip() for value in uncertainties if isinstance(value, str) and value.strip()] if isinstance(uncertainties, list) else [],
    ).model_dump()
