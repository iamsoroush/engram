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
from typing import Any

from ai_engine.core.gateway import gateway_client, resolve_model
from ai_engine.core.text import normalize_bcp47_lang
from ai_engine.core.media import (
    CAPTION_PRODUCT_LABEL_MAX_EDGE,
    downscale_image_for_caption,
    image_to_data_url,
)
from ai_engine.core.structured import (
    call_with_validation_retry,
    correction_message,
    response_format,
    structured_outputs_enabled,
)
# The caption contract (clean caption + pairing/OOC attributes) — shaping lives in ``contracts.caption``;
# re-exported here so the ``processing`` shim and tests keep importing these names from the job module.
from ai_engine.contracts.caption import (  # noqa: F401
    CAPTION_OUTPUT_VERSION,
    PAIRING_LATERALITIES,
    PAIRING_PHASES,
    caption_json_schema,
    normalize_caption_pairing,
    parse_caption_output,
)
# The prompt lives in its own versioned module (§3.3); ``caption_prompt`` is re-exported for the shim
# + tests, and the envelope stamps ``CAPTION_PROMPT_VERSION``.
from ai_engine.prompts.caption import PROMPT_VERSION as CAPTION_PROMPT_VERSION
from ai_engine.prompts.caption import build as caption_prompt  # noqa: F401
from ai_engine.jobs.captures_common import CaptureProcessingOutput, capture_processing_output

# Below this the model's own confidence is treated as "AI unsure" and the backend raises a review.
CAPTION_LOW_CONFIDENCE_THRESHOLD = 0.5


def _request_caption(
    content: bytes,
    media_type: str | None,
    enrichment_context: dict[str, Any] | None,
    *,
    model: str,
    detail: str,
    ai_models: dict[str, Any] | None,
    escalate: bool = False,
) -> dict[str, Any] | None:
    """One structured caption pass at a given image detail level (§3.2 structured output + retry)."""
    client = gateway_client("caption")

    def invoke(call_model: str, _effort: str | None, correction: str | None) -> str:
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": caption_prompt(enrichment_context)},
                    {"type": "image_url", "image_url": {"url": image_to_data_url(content, media_type), "detail": detail}},
                ],
            }
        ]
        request: dict[str, Any] = {"model": call_model, "messages": messages}
        if structured_outputs_enabled():
            request["response_format"] = response_format("caption_output", caption_json_schema())
        if correction is not None:
            messages.append(correction_message(correction))
        response = client.chat.completions.create(**request)
        return response.choices[0].message.content or ""

    return call_with_validation_retry(
        task="caption", ai_models=ai_models, model=model, effort=None, invoke=invoke,
        parse=parse_caption_output, escalate=escalate,
    )


def caption_image_content(
    content: bytes,
    media_type: str | None,
    enrichment_context: dict[str, Any] | None = None,
    *,
    model: str | None = None,
    ai_models: dict[str, Any] | None = None,
    escalate: bool = False,
) -> dict[str, Any] | None:
    """Caption a clinical image through the gateway; None when the model returns no usable caption.

    Worker-side downscale first (bounded longest edge, JPEG q80, detail:low). When the first pass
    flags the image as a product label, re-read it at a higher resolution with detail:high so the
    lot/brand text is legible — that high-detail caption (which carries the lot) wins, but the
    first pass's pairing attributes are preserved.
    """
    resolved_model = resolve_model("caption", ai_models, override=model)
    standard_bytes, standard_mime = downscale_image_for_caption(content, media_type)
    parsed = _request_caption(standard_bytes, standard_mime, enrichment_context, model=resolved_model, detail="low", ai_models=ai_models, escalate=escalate)
    if parsed is None:
        return None
    if parsed.get("pairing", {}).get("isProductLabel") is True:
        label_bytes, label_mime = downscale_image_for_caption(content, media_type, max_edge=CAPTION_PRODUCT_LABEL_MAX_EDGE)
        high_detail = _request_caption(label_bytes, label_mime, enrichment_context, model=resolved_model, detail="high", ai_models=ai_models, escalate=escalate)
        if high_detail is not None:
            high_detail["pairing"] = {**parsed.get("pairing", {}), **high_detail.get("pairing", {}), "isProductLabel": True}
            return high_detail
    return parsed


def caption_output_metadata(
    job: dict[str, Any], caption_result: dict[str, Any], *, lang: str | None = None
) -> CaptureProcessingOutput:
    """Build the completed photo-caption envelope from the structured caption result.

    Carries the free-text caption as `text` (so the existing report/caption readers keep working) PLUS
    the optional attributes: `intents.out_of_context` (reuses the backend OOC path), `pairing`
    attributes (the deterministic backend pairing step consumes these), the model's `confidence`,
    `uncertainties` (the backend raises a needs-review chip below the confidence threshold / on these),
    and a BCP-47 `lang` stamp of the caption's display language (schema-v2 §4.6).
    """
    output = capture_processing_output(job, caption_result.get("caption") or "")
    output["schemaVersion"] = CAPTION_OUTPUT_VERSION
    output["promptVersion"] = CAPTION_PROMPT_VERSION
    if lang is not None:
        output["lang"] = lang
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
