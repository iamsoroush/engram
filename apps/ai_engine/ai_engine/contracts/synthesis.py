"""Session-synthesis contract (the A↔B contract): report sections + performed treatments together.

The keystone Pro output. ``parse_session_synthesis_output`` returns None on empty/malformed content so
the caller emits the skip sentinel and the deterministic baseline stands. All fixed section ids are
always present, in order; safety flags err toward inclusion (only structurally-unusable items drop).
This tolerance is the contract and is preserved here byte-for-byte.
"""
from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ai_engine.core.util import clamp_confidence, utc_now

SESSION_SYNTHESIS_OUTPUT_VERSION = "2026-06-15.session-synthesis-output.v1"

# Fixed section ids + order (rendered by the backend). `treatment-performed` is a PROSE MIRROR of
# treatments[] — the backend re-renders it FROM treatments[] so prose + store can never diverge.
SYNTHESIS_SECTIONS: tuple[tuple[str, str], ...] = (
    ("visit-summary", "Visit summary"),
    ("concern-goals", "Concern & goals"),
    ("assessment", "Assessment"),
    ("treatment-performed", "Treatment performed"),
    ("media", "Media"),
    ("plan-followup", "Plan & follow-up"),
    ("aftercare", "Aftercare"),
)
SYNTHESIS_SECTION_IDS: tuple[str, ...] = tuple(section_id for section_id, _ in SYNTHESIS_SECTIONS)
SYNTHESIS_LANGUAGES = {"fa", "en", "mixed"}

# Persian section titles (report_language="fa"). The body prose already follows reportLanguage; the
# fixed section TITLES must too, or a Persian report shows English headings.
SYNTHESIS_SECTION_TITLES_FA: dict[str, str] = {
    "visit-summary": "خلاصه ویزیت",
    "concern-goals": "نگرانی‌ها و اهداف",
    "assessment": "ارزیابی",
    "treatment-performed": "درمان انجام‌شده",
    "media": "تصاویر",
    "plan-followup": "برنامه و پیگیری",
    "aftercare": "مراقبت‌های بعد از درمان",
}


class TreatmentItem(BaseModel):
    """One performed treatment (the B side of the A↔B contract)."""

    model_config = ConfigDict(extra="ignore")

    area: str
    product: str
    brand: str | None = None
    quantity: int | float | None = None
    unit: str | None = None
    quantityText: str | None = None
    lot: str | None = None
    confidence: float
    sourceCaptureIds: list[str]
    evidence: str | None = None
    carriedForward: bool
    supersedesCaptureId: str | None = None
    attributes: dict[str, Any]


class AftercareSelection(BaseModel):
    """A clinic aftercare protocol the model judged applicable to this visit."""

    model_config = ConfigDict(extra="ignore")

    templateId: str
    status: str
    note: str | None = None


class SafetyFlag(BaseModel):
    """A detected allergy / contraindication / consent statement (clinical text, never translated)."""

    model_config = ConfigDict(extra="ignore")

    kind: str
    text: str
    sourceCaptureIds: list[str]


class Section(BaseModel):
    """A fixed report section with ordered paragraph/image blocks."""

    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    blocks: list[dict[str, Any]]


class SessionSynthesisOutput(BaseModel):
    """The validated single-pass synthesis output (the full A↔B contract)."""

    model_config = ConfigDict(extra="ignore")

    schemaVersion: str
    summary: str
    language: str
    sections: list[dict[str, Any]]
    treatments: list[dict[str, Any]]
    sourceReferences: list[dict[str, Any]]
    uncertainties: list[str]
    aftercareSelections: list[dict[str, Any]]
    safetyFlags: list[dict[str, Any]]
    generatedBy: str
    generatedAt: str


def synthesis_section_title(section_id: str, default_title: str, report_language: str | None) -> str:
    """Return the section title localized to the report language (English title by default)."""
    if isinstance(report_language, str) and report_language.strip().lower().startswith("fa"):
        return SYNTHESIS_SECTION_TITLES_FA.get(section_id, default_title)
    return default_title


def _clean_synthesis_blocks(raw_blocks: Any) -> list[dict[str, Any]]:
    """Coerce model block output into validated paragraph/image blocks."""
    blocks: list[dict[str, Any]] = []
    if not isinstance(raw_blocks, list):
        return blocks
    for block in raw_blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "paragraph":
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                blocks.append({"type": "paragraph", "text": text.strip()})
        elif block_type == "image":
            capture_id = block.get("captureId")
            if isinstance(capture_id, str) and capture_id.strip():
                image: dict[str, Any] = {"type": "image", "captureId": capture_id.strip()}
                caption = block.get("caption")
                if isinstance(caption, str) and caption.strip():
                    image["caption"] = caption.strip()
                blocks.append(image)
    return blocks


def _clean_synthesis_treatment(raw: Any) -> dict[str, Any] | None:
    """Coerce one TreatmentItem into the stable core+attributes shape, or None if unusable."""
    if not isinstance(raw, dict):
        return None
    area = raw.get("area")
    product = raw.get("product")
    if not (isinstance(area, str) and area.strip()) and not (isinstance(product, str) and product.strip()):
        return None

    def _text(value: Any) -> str | None:
        return value.strip() if isinstance(value, str) and value.strip() else None

    def _number(value: Any) -> float | int | None:
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    source_ids = raw.get("sourceCaptureIds")
    attributes = raw.get("attributes")
    return TreatmentItem(
        area=_text(area) or "",
        product=_text(product) or "",
        brand=_text(raw.get("brand")),
        quantity=_number(raw.get("quantity")),
        unit=_text(raw.get("unit")),
        quantityText=_text(raw.get("quantityText")),
        lot=_text(raw.get("lot")),
        confidence=clamp_confidence(raw.get("confidence")),
        sourceCaptureIds=[str(value) for value in source_ids if isinstance(value, str)] if isinstance(source_ids, list) else [],
        evidence=_text(raw.get("evidence")),
        carriedForward=raw.get("carriedForward") is True,
        supersedesCaptureId=_text(raw.get("supersedesCaptureId")),
        attributes=attributes if isinstance(attributes, dict) else {},
    ).model_dump()


def _clean_aftercare_selections(raw: Any) -> list[dict[str, Any]]:
    """Coerce the model's aftercare matches into validated {templateId, status, note} items."""
    selections: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return selections
    for item in raw:
        if not isinstance(item, dict):
            continue
        template_id = item.get("templateId")
        status = item.get("status")
        if not isinstance(template_id, str) or not template_id.strip():
            continue
        if status not in {"applies", "conflicts", "superseded"}:
            continue
        note = item.get("note")
        selections.append(
            AftercareSelection(
                templateId=template_id, status=status, note=note if isinstance(note, str) and note.strip() else None
            ).model_dump()
        )
    return selections


def _clean_safety_flags(raw: Any) -> list[dict[str, Any]]:
    """Coerce the model's safety flags into validated {kind, text, sourceCaptureIds} items.

    Safety errs toward inclusion (opt-out): a flag the model surfaced is kept — the clinician removes a
    wrong one downstream. We only drop items that are structurally unusable (unknown kind, empty text).
    """
    flags: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return flags
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        text = item.get("text")
        if kind not in {"allergy", "contraindication", "consent"}:
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        source_ids = item.get("sourceCaptureIds")
        flags.append(
            SafetyFlag(
                kind=kind,
                text=text.strip(),
                sourceCaptureIds=[str(value) for value in source_ids if isinstance(value, str)]
                if isinstance(source_ids, list)
                else [],
            ).model_dump()
        )
    return flags


def parse_session_synthesis_output(
    raw_text: str, *, source_capture_ids: list[str] | None = None, report_language: str | None = None
) -> dict[str, Any] | None:
    """Parse + validate the synthesis JSON into the A↔B contract, or None to fall back.

    Returns the full output with ALL fixed section ids present (in order), cleaned treatments, and
    `sourceReferences` covering every reportable capture so the backend can mark contributions.
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
    if not isinstance(parsed, dict):
        return None
    summary = parsed.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None

    raw_sections = parsed.get("sections")
    blocks_by_id: dict[str, list[dict[str, Any]]] = {}
    if isinstance(raw_sections, list):
        for section in raw_sections:
            if isinstance(section, dict) and isinstance(section.get("id"), str):
                blocks_by_id[section["id"]] = _clean_synthesis_blocks(section.get("blocks"))
    sections = [
        Section(
            id=section_id,
            title=synthesis_section_title(section_id, title, report_language),
            blocks=blocks_by_id.get(section_id, []),
        ).model_dump()
        for section_id, title in SYNTHESIS_SECTIONS
    ]

    treatments = [cleaned for cleaned in (_clean_synthesis_treatment(item) for item in (parsed.get("treatments") or [])) if cleaned]
    language = parsed.get("language") if parsed.get("language") in SYNTHESIS_LANGUAGES else "mixed"
    uncertainties = parsed.get("uncertainties")
    source_references = [{"type": "capture", "captureId": capture_id} for capture_id in (source_capture_ids or [])]
    return SessionSynthesisOutput(
        schemaVersion=SESSION_SYNTHESIS_OUTPUT_VERSION,
        summary=summary.strip(),
        language=language,
        sections=sections,
        treatments=treatments,
        sourceReferences=source_references,
        uncertainties=[str(value) for value in uncertainties if isinstance(value, str)] if isinstance(uncertainties, list) else [],
        aftercareSelections=_clean_aftercare_selections(parsed.get("aftercareSelections")),
        safetyFlags=_clean_safety_flags(parsed.get("safetyFlags")),
        generatedBy="ai-engine",
        generatedAt=utc_now().isoformat(),
    ).model_dump()
