"""Photo capture job: Pro image captioning + attribute extraction.

Photo captioning is a Pro-tier capability (see the tier table in docs/intelligence-layer.md §3).
The backend gates it: it attaches an `enrichmentContext` to a PHOTO worker payload only for Pro
tenants, so a Basic tenant never incurs a gateway call and keeps a blank caption (manual add).
The worker stays a pure function of its payload — it captions iff an `enrichmentContext` is
present and a gateway is configured, and leaves the caption blank otherwise. The caption is a
structured result: free-text `caption` PLUS optional attributes (out-of-context + pairing).
Notes are NOT enriched here — they are a pure passthrough (see `run_capture_processing_job`).

Worker-side downscale: vision token cost/latency scale with pixel count, so we re-encode the upload
to a bounded-longest-edge JPEG before sending (detail:low). A product-label shot is re-read at a
higher resolution with detail:high so the lot/brand text stays legible.
"""
import json
import re
from typing import Any

from ai_engine.core.domain import domain_framing
from ai_engine.core.gateway import gateway_client, gateway_settings_for
from ai_engine.core.media import (
    CAPTION_PRODUCT_LABEL_MAX_EDGE,
    downscale_image_for_caption,
    image_to_data_url,
)
from ai_engine.core.text import enrichment_language_directive, normalize_digits_to_latin
from ai_engine.core.util import clamp_confidence
from ai_engine.jobs.captures_common import CaptureProcessingOutput, capture_processing_output

# Below this the model's own confidence is treated as "AI unsure" and the backend raises a review.
CAPTION_LOW_CONFIDENCE_THRESHOLD = 0.5
PAIRING_LATERALITIES = {"left", "right", "bilateral", "midline", "central"}
PAIRING_PHASES = {"before", "after", "during", "intraop", "other"}


def caption_prompt(enrichment_context: dict[str, Any] | None) -> str:
    """Build the instruction prompt for photo description + attribute extraction.

    The caption is a NEUTRAL textual stand-in for the image (so downstream text-only AI jobs can read
    the photo) — an objective description of what is visibly present, NOT a clinical assessment. It is
    structured JSON: a free-text `caption` PLUS optional attributes — out-of-context detection (reuses
    the OOC path) and pairing attributes (region/laterality/view/phase + isProductLabel) that the
    backend turns into before/after pairs deterministically. Vertical-agnostic via the domain
    descriptor; a product-label shot reads the lot/brand text into the caption.
    """
    context = enrichment_context if isinstance(enrichment_context, dict) else {}
    # Vertical-aware framing; neutral "clinic" + no feature examples when absent.
    label, _, caption_findings = domain_framing(context)
    findings_hint = f" (e.g. {', '.join(caption_findings)})" if caption_findings else ""
    return "\n\n".join(
        (
            f"You describe photos for Engram, a clinical memory system, turning each photo into a faithful "
            f"text description that can stand in for the image in later processing. The setting is a {label}. "
            "You are an OBJECTIVE describer, not a diagnostician.",
            (
                "Look at the image and return a STRICT JSON object (no markdown, no code fences) with these keys:\n"
                "- caption: one or two sentences describing OBJECTIVELY what is VISIBLY PRESENT. Lead with the photo's "
                "PRIMARY subject (the patient's anatomy, OR a product/medication). Give the anatomical area and view "
                f"plus any clinically relevant features that are actually visible{findings_hint}, AND note any "
                "product/medication that is visible even if it is only in the background. For ANY visible "
                "product/medication label or box, read its BRAND and LOT/batch number into the caption. Do NOT "
                "diagnose, assess severity, judge outcomes, or state what is absent or normal (never write "
                "\"no signs of …\"). Describe only what is there. Do NOT invent patient identity, measurements, "
                "dates, or anything not visible.\n"
                "- confidence: a number 0..1 for how confident you are in the caption (low when the image is blurry, "
                "ambiguous, or hard to read).\n"
                "- outOfContext: {present: boolean, reason: string|null, confidence: 0..1} — present=true only when the "
                "image has no clinical/visit relevance (e.g. a random screenshot, a parking receipt).\n"
                "- pairing: {region: string|null, laterality: \"left|right|bilateral|midline|central|null\", "
                "view: string|null, phase: \"before|after|during|null\", isProductLabel: boolean}. isProductLabel "
                "reflects the photo's PRIMARY INTENT: set it true ONLY when the main subject is a product/medication/"
                "label (the photo's purpose is to document the product or its lot), NOT when a product merely appears "
                "in the background of a clinical photo of the patient. For a patient photo fill the anatomical "
                "attributes (region/laterality/view/phase); for a product photo leave them null.\n"
                "- uncertainties: a list of short human-readable sentences for anything a clinician should confirm "
                "(unreadable lot number, ambiguous area). Use [] when there is nothing to confirm.\n"
                "- display: the SAME caption text rendered as Markdown, with ONLY the 1-4 most important words "
                "or phrases wrapped in **bold** (e.g. the brand, the lot/batch number, the anatomical area, or a "
                "key visible feature). Do NOT change any wording, punctuation, or order — add nothing but the ** "
                "markers. If nothing stands out, return the caption text unchanged.\n"
                f"{enrichment_language_directive(context)} "
                "Keep brand NAMES verbatim, but ALWAYS render NUMBERS — lot/batch numbers, doses, quantities, and "
                "dates — in Western/Latin digits (0-9) even when the caption prose is in Persian, so they stay "
                "comparable across captures (this is digit normalization, not romanizing words). Leave any attribute "
                "null/false rather than guessing."
            ),
            f"Clinic/visit context:\n{json.dumps(context, ensure_ascii=False, sort_keys=True)}",
        )
    )


def normalize_caption_pairing(raw: Any) -> dict[str, Any]:
    """Coerce model pairing output into the stable {region,laterality,view,phase,isProductLabel} shape."""
    pairing = raw if isinstance(raw, dict) else {}

    def _text(value: Any) -> str | None:
        return value.strip().lower() if isinstance(value, str) and value.strip() else None

    laterality = _text(pairing.get("laterality"))
    phase = _text(pairing.get("phase"))
    return {
        "region": pairing.get("region").strip() if isinstance(pairing.get("region"), str) and pairing.get("region").strip() else None,
        "laterality": laterality if laterality in PAIRING_LATERALITIES else None,
        "view": pairing.get("view").strip() if isinstance(pairing.get("view"), str) and pairing.get("view").strip() else None,
        "phase": phase if phase in PAIRING_PHASES else None,
        "isProductLabel": pairing.get("isProductLabel") is True,
    }


def _caption_display_text(raw_display: Any, caption_text: str) -> str:
    """Return the model's Markdown display variant of the caption — but only when it is the SAME text
    with just **bold** added (verified by stripping the markers). Falls back to the clean caption so
    the UI never shows wording that diverged from the data text. Digits are normalized to match.
    """
    if not isinstance(raw_display, str) or not raw_display.strip():
        return caption_text
    candidate = normalize_digits_to_latin(raw_display.strip())

    def _plain(value: str) -> str:
        return re.sub(r"\s+", " ", value.replace("**", "")).strip().lower()

    return candidate if _plain(candidate) == _plain(caption_text) else caption_text


def parse_caption_output(raw_text: str) -> dict[str, Any] | None:
    """Parse the structured caption JSON; degrade to plain-text caption when it isn't JSON.

    Returns ``{caption, display, confidence, outOfContext, pairing, uncertainties}`` or None when there
    is no usable caption text. `caption` is the CLEAN text consumed by downstream AI jobs; `display` is
    the model's Markdown-bolded variant for the UI only. A gateway that returns a bare caption string
    (no JSON) still works — the raw text becomes both caption and display, with no attributes.
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
        return {"caption": plain, "display": plain, "confidence": None, "outOfContext": None, "pairing": normalize_caption_pairing(None), "uncertainties": []}
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
    return {
        "caption": caption_text,
        "display": _caption_display_text(parsed.get("display"), caption_text),
        "confidence": clamp_confidence(confidence) if isinstance(confidence, int | float) and not isinstance(confidence, bool) else None,
        "outOfContext": out_of_context,
        "pairing": normalize_caption_pairing(parsed.get("pairing")),
        "uncertainties": [str(value).strip() for value in uncertainties if isinstance(value, str) and value.strip()] if isinstance(uncertainties, list) else [],
    }


def _request_caption(
    content: bytes,
    media_type: str | None,
    enrichment_context: dict[str, Any] | None,
    *,
    model: str | None,
    detail: str,
) -> dict[str, Any] | None:
    """One structured caption pass at a given image detail level."""
    client = gateway_client("caption")
    response = client.chat.completions.create(
        model=model or gateway_settings_for("caption")[2],
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": caption_prompt(enrichment_context)},
                    {"type": "image_url", "image_url": {"url": image_to_data_url(content, media_type), "detail": detail}},
                ],
            }
        ],
    )
    text = response.choices[0].message.content
    return parse_caption_output(text) if text and text.strip() else None


def caption_image_content(
    content: bytes,
    media_type: str | None,
    enrichment_context: dict[str, Any] | None = None,
    *,
    model: str | None = None,
) -> dict[str, Any] | None:
    """Caption a clinical image through the gateway; None when the model returns no usable caption.

    Worker-side downscale first (bounded longest edge, JPEG q80, detail:low). When the first pass
    flags the image as a product label, re-read it at a higher resolution with detail:high so the
    lot/brand text is legible — that high-detail caption (which carries the lot) wins, but the
    first pass's pairing attributes are preserved.
    """
    standard_bytes, standard_mime = downscale_image_for_caption(content, media_type)
    parsed = _request_caption(standard_bytes, standard_mime, enrichment_context, model=model, detail="low")
    if parsed is None:
        return None
    if parsed.get("pairing", {}).get("isProductLabel") is True:
        label_bytes, label_mime = downscale_image_for_caption(content, media_type, max_edge=CAPTION_PRODUCT_LABEL_MAX_EDGE)
        high_detail = _request_caption(label_bytes, label_mime, enrichment_context, model=model, detail="high")
        if high_detail is not None:
            high_detail["pairing"] = {**parsed.get("pairing", {}), **high_detail.get("pairing", {}), "isProductLabel": True}
            return high_detail
    return parsed


def caption_output_metadata(job: dict[str, Any], caption_result: dict[str, Any]) -> CaptureProcessingOutput:
    """Build the completed photo-caption envelope from the structured caption result.

    Carries the free-text caption as `text` (so the existing report/caption readers keep working) PLUS
    the optional attributes: `intents.out_of_context` (reuses the backend OOC path), `pairing`
    attributes (the deterministic backend pairing step consumes these), the model's `confidence`, and
    `uncertainties` (the backend raises a needs-review chip below the confidence threshold / on these).
    """
    output = capture_processing_output(job, caption_result.get("caption") or "")
    out_of_context = caption_result.get("outOfContext")
    if isinstance(out_of_context, dict) and out_of_context.get("present") is True:
        # Match the transcription intent shape so `out_of_context_marker` reads it unchanged.
        output["intents"] = {"out_of_context": {"present": True, **{k: v for k, v in out_of_context.items() if k != "present"}}}
    pairing = caption_result.get("pairing")
    if isinstance(pairing, dict):
        output["pairing"] = pairing
    confidence = caption_result.get("confidence")
    if isinstance(confidence, int | float) and not isinstance(confidence, bool):
        output["confidence"] = float(confidence)
    uncertainties = caption_result.get("uncertainties")
    if isinstance(uncertainties, list) and uncertainties:
        output["uncertainties"] = [str(value) for value in uncertainties if isinstance(value, str)]
    # The Markdown display variant for the UI (the clean caption is `text`, consumed by AI jobs).
    display = caption_result.get("display")
    if isinstance(display, str) and display.strip() and display.strip() != (caption_result.get("caption") or "").strip():
        output["display"] = display
    return output
