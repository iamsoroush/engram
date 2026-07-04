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
from typing import Any

from ai_engine.core.domain import domain_framing
from ai_engine.core.gateway import gateway_client, gateway_settings_for
from ai_engine.core.media import (
    CAPTION_PRODUCT_LABEL_MAX_EDGE,
    downscale_image_for_caption,
    image_to_data_url,
)
from ai_engine.core.text import enrichment_language_directive
# The caption contract (clean caption + pairing/OOC attributes) — shaping lives in ``contracts.caption``;
# re-exported here so the ``processing`` shim and tests keep importing these names from the job module.
from ai_engine.contracts.caption import (  # noqa: F401
    CAPTION_OUTPUT_VERSION,
    PAIRING_LATERALITIES,
    PAIRING_PHASES,
    normalize_caption_pairing,
    parse_caption_output,
)
from ai_engine.jobs.captures_common import CaptureProcessingOutput, capture_processing_output

# Below this the model's own confidence is treated as "AI unsure" and the backend raises a review.
CAPTION_LOW_CONFIDENCE_THRESHOLD = 0.5


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
    output["schemaVersion"] = CAPTION_OUTPUT_VERSION
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
