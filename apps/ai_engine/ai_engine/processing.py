import base64
import json
import re
import subprocess
from datetime import datetime, timezone
from io import BytesIO
from time import sleep
from typing import Any, Literal, NotRequired, TypedDict

import httpx
from openai import OpenAI

try:  # Pillow is used to downscale photos before captioning; degrade gracefully if absent.
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover - exercised only in a Pillow-less environment
    Image = None
    ImageOps = None

from ai_engine.config import settings


class DetectedPatientOutput(TypedDict):
    """Future-ready patient detection result for capture processors."""

    status: Literal["detected", "not_detected", "uncertain"]
    full_name: str | None
    national_id: str | None
    confidence: float | None
    evidence: str | None
    source_text: str | None


class CaptureProcessingOutput(TypedDict, total=False):
    """Stable capture-processing output shape written into capture metadata."""

    status: str
    text: str
    generated_by: str
    job_id: str
    job_type: str
    generated_at: str
    source_artifact_ids: list[str]
    detected_patient: NotRequired[DetectedPatientOutput]
    language: NotRequired[str]
    patient_information: NotRequired[dict[str, Any]]
    clinical_summary: NotRequired[str | None]
    uncertainties: NotRequired[list[str]]
    intents: NotRequired[dict[str, Any] | None]
    pairing: NotRequired[dict[str, Any]]
    confidence: NotRequired[float]
    display: NotRequired[str]


NOT_DETECTED_PATIENT: DetectedPatientOutput = {
    "status": "not_detected",
    "full_name": None,
    "national_id": None,
    "confidence": None,
    "evidence": None,
    "source_text": None,
}

TEST_CAPTURE_TEXT_BY_FILENAME = {
    "audio_01_initial_consultation.wav": "Patient Sara Nazari came for a follow-up after cheek filler. She reports mild asymmetry on the left cheek and wants a conservative correction. No pain, no fever, and no allergy was reported.",
    "photo_01_pre_correction_left_cheek.jpg": "Pre-correction image showing mild left cheek asymmetry before touch-up.",
    "text_note_01.txt": "Patient prefers subtle correction and does not want visible overfilling. Conservative approach requested. Aftercare instructions were given. Patient should send a follow-up photo in 2 weeks if asymmetry persists.",
    "audio_02_procedure_note.wav": "Injected 0.3 mL hyaluronic acid filler into the left mid cheek. Used cannula technique. Patient tolerated the procedure well. Advised no massage and avoid heavy exercise for 24 hours.",
    "photo_02_post_correction_left_cheek.jpg": "Post-correction image showing improved left cheek contour after conservative correction.",
}

TEST_FINAL_SUMMARY = "Follow-up cheek filler correction for mild left cheek asymmetry. Conservative 0.3 mL hyaluronic acid filler touch-up was performed in the left mid cheek using cannula technique. Patient tolerated the procedure well and received aftercare instructions."

TRANSCRIPTION_LANGUAGES = {"fa", "en", "mixed", "unknown"}

ASSIGNMENT_INTENT_BASES = {"explicit", "implicit"}

TRANSCRIPTION_LANGUAGE_NAMES = {
    "fa": "Persian (Farsi)",
    "en": "English",
    "ar": "Arabic",
}


def transcription_language_directive(transcription_context: dict[str, Any] | None) -> str:
    """Instruct the model on transcript language/script.

    Default ('auto') transcribes verbatim in the original script — this prevents Persian speech
    from coming back romanized in Latin, which otherwise breaks name matching and reassignment.
    A specific preferred language asks the model to transcribe in that language's native script.
    """
    context = transcription_context if isinstance(transcription_context, dict) else {}
    preferred = str(context.get("preferredLanguage") or "auto").strip().lower()
    if preferred and preferred not in {"auto", "unknown", "mixed"}:
        name = TRANSCRIPTION_LANGUAGE_NAMES.get(preferred, preferred)
        return (
            f"The clinic's preferred transcription language is {name}: write the transcript in {name} using its "
            "native script. Do not translate into another language and do not romanize."
        )
    return (
        "Transcribe VERBATIM in whatever language(s) are actually spoken, preserving the ORIGINAL SCRIPT — "
        "Persian/Farsi speech MUST be written in Persian script (e.g. «بیمار را عوض کن به سروش»), never romanized "
        "Latin (not «Bimar ro avaz kon be Soroush»). Never translate the transcript and never romanize it."
    )

PATIENT_INFORMATION_FIELDS = (
    "raw_mentioned_name",
    "standardized_display_name",
    "alternate_transliterations",
    "national_id",
    "phone",
    "date_of_birth",
    "evidence",
    "confidence",
)


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(timezone.utc)


def output_key_for_capture(capture_type: str) -> str:
    """Return the metadata field written by a completed capture job."""
    if capture_type == "audio":
        return "transcript"
    if capture_type == "photo":
        return "caption"
    # Notes are a pure passthrough (no decoration): the job marks the note processed with its RAW
    # text under `note_text`, preserving chain ordering + report_contribution wiring. The report
    # itself reads the raw `detail`, so this envelope only carries provenance.
    return "note_text"


def placeholder_text_for_capture(capture: dict[str, Any]) -> str:
    """Build deterministic placeholder output until real AI processors land."""
    metadata = capture.get("metadata") if isinstance(capture.get("metadata"), dict) else {}
    filename = str(metadata.get("original_filename") or "").strip()
    if filename in TEST_CAPTURE_TEXT_BY_FILENAME:
        return TEST_CAPTURE_TEXT_BY_FILENAME[filename]
    detail = str(metadata.get("detail") or "").strip()
    capture_type = capture.get("type")
    if capture_type == "audio":
        raise RuntimeError("Audio transcription gateway is not configured")
    if capture_type == "photo":
        return "Caption placeholder. Image capture processing completed successfully."
    if detail:
        normalized_detail = " ".join(detail.split())
        if "Patient prefers subtle correction" in normalized_detail and "follow-up photo in 2 weeks" in normalized_detail:
            return TEST_CAPTURE_TEXT_BY_FILENAME["text_note_01.txt"]
        return detail
    return "Text placeholder. Text capture processing completed successfully."


def capture_detected_patient(capture: dict[str, Any], text: str) -> DetectedPatientOutput | None:
    """Return schema-ready patient detection output without performing detection."""
    if capture.get("type") != "audio":
        return None
    # TODO(ai-integration): Replace this deterministic stub with real patient
    # detection, preserving the same status/full_name/national_id/confidence
    # and evidence/source_text fields for later session assignment.
    return {**NOT_DETECTED_PATIENT, "source_text": text}


def completed_metadata(job: dict[str, Any], capture: dict[str, Any]) -> CaptureProcessingOutput:
    """Return metadata for a completed placeholder capture processor."""
    text = placeholder_text_for_capture(capture)
    output = capture_processing_output(job, text)
    detected_patient = capture_detected_patient(capture, text)
    if detected_patient is not None:
        output["detected_patient"] = detected_patient
    return output


def partial_metadata(job: dict[str, Any], capture: dict[str, Any]) -> CaptureProcessingOutput:
    """Return deterministic in-progress capture output."""
    capture_type = capture.get("type")
    label = "Transcribing" if capture_type == "audio" else "Reading image" if capture_type == "photo" else "Structuring note"
    text = f"{label} audio..." if capture_type == "audio" else f"{label} placeholder output..."
    output: CaptureProcessingOutput = {
        "status": "processing",
        "text": text,
        "generated_by": "ai-engine",
        "job_id": job["id"],
        "job_type": job["jobType"],
        "generated_at": utc_now().isoformat(),
        "source_artifact_ids": job.get("inputArtifactIds") or [],
    }
    if capture_type == "audio":
        output["detected_patient"] = {**NOT_DETECTED_PATIENT}
    return output


def transcription_is_configured() -> bool:
    """Return whether a real audio transcription gateway is configured."""
    return bool(settings.transcription_base_url.strip())


def empty_patient_information(*, source_text: str | None = None) -> dict[str, Any]:
    """Return the generated patient-information schema for no detected identity."""
    return {
        "raw_mentioned_name": None,
        "standardized_display_name": None,
        "alternate_transliterations": [],
        "national_id": None,
        "phone": None,
        "date_of_birth": None,
        "evidence": None,
        "confidence": 0.0,
        "source_text": source_text,
    }


def detected_patient_from_patient_information(patient_information: dict[str, Any], transcript: str) -> DetectedPatientOutput:
    """Return the legacy detected-patient shape from structured patient information."""
    name = patient_information.get("standardized_display_name") or patient_information.get("raw_mentioned_name")
    confidence = patient_information.get("confidence")
    return {
        "status": "detected" if name or patient_information.get("national_id") else "not_detected",
        "full_name": str(name) if name else None,
        "national_id": str(patient_information.get("national_id")) if patient_information.get("national_id") else None,
        "confidence": float(confidence) if isinstance(confidence, int | float) else None,
        "evidence": str(patient_information.get("evidence")) if patient_information.get("evidence") else None,
        "source_text": transcript,
    }


def structured_transcription_from_text(text: str, *, language: str = "en") -> dict[str, Any]:
    """Return deterministic structured transcription for fixtures and fallback output."""
    return {
        "transcript": text,
        "language": language,
        "patient_information": empty_patient_information(source_text=text),
        "clinical_summary": None,
        "uncertainties": [],
        "intents": None,
    }


def clamp_confidence(value: Any) -> float:
    """Clamp a model-provided confidence into [0.0, 1.0], defaulting to 0.0."""
    return max(0.0, min(float(value), 1.0)) if isinstance(value, int | float) else 0.0


def normalize_intents(raw: Any) -> dict[str, Any] | None:
    """Normalize best-effort intent classification, dropping absent or malformed intents.

    The transcript is the required, high-trust field; intents are optional so a malformed
    intent payload never invalidates an otherwise usable transcript.
    """
    if not isinstance(raw, dict):
        return None
    intents: dict[str, Any] = {}
    assignment = raw.get("assignment")
    if isinstance(assignment, dict) and assignment.get("present") is True:
        basis = assignment.get("basis")
        evidence = assignment.get("evidence")
        intents["assignment"] = {
            "present": True,
            "basis": basis if basis in ASSIGNMENT_INTENT_BASES else "implicit",
            "confidence": clamp_confidence(assignment.get("confidence")),
            "evidence": str(evidence).strip() if isinstance(evidence, str) and evidence.strip() else None,
        }
    append = raw.get("append")
    if isinstance(append, dict) and append.get("present") is True:
        intents["append"] = {"present": True, "confidence": clamp_confidence(append.get("confidence"))}
    out_of_context = raw.get("out_of_context")
    if isinstance(out_of_context, dict) and out_of_context.get("present") is True:
        reason = out_of_context.get("reason")
        intents["out_of_context"] = {
            "present": True,
            "confidence": clamp_confidence(out_of_context.get("confidence")),
            "reason": str(reason).strip() if isinstance(reason, str) and reason.strip() else None,
        }
    return intents or None


def domain_framing(context: dict[str, Any] | None) -> tuple[str, list[str], list[str]]:
    """Extract vertical-aware prompt framing from a job context/payload.

    Vertical-AGNOSTIC by contract: the backend supplies a `domain` descriptor
    (`app/services/verticals.py:domain_descriptor`) carrying the setting `label` and optional
    `vocabulary` / `captionFindings` hints. When it is absent this returns a neutral "clinic"
    default with no vocabulary — so a worker prompt NEVER hardcodes or assumes a vertical. Any
    vertical-specific wording must come through this descriptor (i.e. be optional + data-driven).
    """
    domain = context.get("domain") if isinstance(context, dict) and isinstance(context.get("domain"), dict) else {}
    raw_label = domain.get("label")
    label = raw_label.strip() if isinstance(raw_label, str) and raw_label.strip() else "clinic"
    vocabulary = [value for value in (domain.get("vocabulary") or []) if isinstance(value, str)]
    caption_findings = [value for value in (domain.get("captionFindings") or []) if isinstance(value, str)]
    return label, vocabulary, caption_findings


def transcription_prompt(transcription_context: dict[str, Any] | None) -> str:
    """Build the rich instruction prompt for the OpenAI-compatible gateway."""
    context = transcription_context if isinstance(transcription_context, dict) else {}
    configured_prompt = settings.transcription_prompt.strip()
    language_directive = transcription_language_directive(context)
    # Vertical-aware framing supplied by the backend; neutral "clinic" + no vocabulary when absent.
    label, vocabulary, _ = domain_framing(context)
    vocab_line = f"Common {label} vocabulary may include {', '.join(vocabulary)}. " if vocabulary else ""
    return "\n\n".join(
        part
        for part in (
            configured_prompt if configured_prompt and configured_prompt != "Transcribe this audio." else None,
            (
                f"You are transcribing and extracting clinical identity details for Memara, a clinical memory system. The clinical setting is a {label}. "
                "The audio may be Persian/Farsi, English, or mixed. Preserve the transcript faithfully, including clinically relevant filler words when useful. "
                f"{language_directive} "
                "Keep names inside the transcript exactly as spoken (original script); provide a readable English transliteration ONLY in standardized_display_name (with alternates in alternate_transliterations) — do not let that transliteration change the transcript text. "
                "Iranian national IDs and phone numbers may be spoken digit by digit in Persian, Arabic, or English numerals; normalize them to digit strings when explicitly present. "
                f"{vocab_line}"
                "Use the provided context ONLY to spell/transliterate a name that is actually spoken in THIS audio clip — never to introduce or confirm an identity. Set raw_mentioned_name and standardized_display_name ONLY to a patient name spoken in this clip; if no name or identifier is spoken here, both MUST be null with confidence 0, even when the assigned-patient/session context names someone. Never copy the patient's name from context, history, or a previous capture. "
                "Also classify intent in `intents`: set assignment.present=true only when THIS audio clip itself states or mentions which patient the visit is about (a spoken name or identifier) — not based on the provided context. Set basis='explicit' ONLY for a clear instruction to change or correct an existing assignment (for example 'change the patient to X', 'this is actually X not Y', or 'wrong patient, it's X'). Treat any statement of who the patient is as basis='implicit' — this includes a name simply stated or fronted and identity declarations (for example 'Ms. Ghasemi, follow-up', 'the patient is X', 'this is X', or 'I am X'). When unsure, prefer 'implicit'. Set out_of_context.present=true when the audio has no clinical or visit content; set append.present=true when it only adds incremental detail to an ongoing note; use null for any intent you cannot determine. "
                "Return only strict JSON with no markdown."
            ),
            (
                "Required JSON shape: "
                '{"transcript":"string","language":"fa|en|mixed|unknown","patient_information":{"raw_mentioned_name":null,'
                '"standardized_display_name":null,"alternate_transliterations":[],"national_id":null,"phone":null,'
                '"date_of_birth":null,"evidence":null,"confidence":0.0},"clinical_summary":null,"uncertainties":[],'
                '"intents":{"assignment":{"present":false,"basis":"implicit","confidence":0.0,"evidence":null},'
                '"append":{"present":false,"confidence":0.0},"out_of_context":{"present":false,"confidence":0.0,"reason":null}}}'
            ),
            f"Tenant-scoped transcription context:\n{json.dumps(context, ensure_ascii=False, sort_keys=True)}",
        )
        if part
    )


def parse_structured_transcription_output(raw_text: str) -> dict[str, Any]:
    """Parse and validate strict structured transcription JSON."""
    text = raw_text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Audio transcription returned malformed structured JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Audio transcription returned non-object structured JSON")

    transcript = parsed.get("transcript")
    if not isinstance(transcript, str) or not transcript.strip():
        raise RuntimeError("Audio transcription structured JSON is missing transcript")
    # Normalize spoken numbers (doses, national IDs, phones, dates) to Western/Latin digits so all
    # extracted quantification is comparable regardless of the spoken language — a national ID or dose
    # dictated in Persian digits must match a stored Latin one. The prose words stay original script.
    transcript = normalize_digits_to_latin(transcript.strip())
    language = parsed.get("language")
    if language not in TRANSCRIPTION_LANGUAGES:
        language = "unknown"
    patient_information = parsed.get("patient_information")
    if not isinstance(patient_information, dict):
        raise RuntimeError("Audio transcription structured JSON is missing patient_information")

    normalized_patient = empty_patient_information(source_text=transcript)
    for field in PATIENT_INFORMATION_FIELDS:
        if field in patient_information:
            normalized_patient[field] = patient_information[field]
    alternates = normalized_patient.get("alternate_transliterations")
    normalized_patient["alternate_transliterations"] = [str(value) for value in alternates if isinstance(value, str)] if isinstance(alternates, list) else []
    confidence = normalized_patient.get("confidence")
    normalized_patient["confidence"] = max(0.0, min(float(confidence), 1.0)) if isinstance(confidence, int | float) else 0.0
    for field in ("raw_mentioned_name", "standardized_display_name", "national_id", "phone", "date_of_birth", "evidence"):
        value = normalized_patient.get(field)
        normalized_patient[field] = str(value).strip() if value is not None and str(value).strip() else None
    # Identifiers/dates are comparison-critical (patient matching reads national_id/phone) → Latin digits.
    for field in ("national_id", "phone", "date_of_birth"):
        if normalized_patient.get(field):
            normalized_patient[field] = normalize_digits_to_latin(normalized_patient[field])

    uncertainties = parsed.get("uncertainties")
    clinical_summary = parsed.get("clinical_summary")
    return {
        "transcript": transcript,
        "language": language,
        "patient_information": normalized_patient,
        "clinical_summary": normalize_digits_to_latin(clinical_summary.strip()) if isinstance(clinical_summary, str) and clinical_summary.strip() else None,
        "uncertainties": [str(value) for value in uncertainties if isinstance(value, str)] if isinstance(uncertainties, list) else [],
        "intents": normalize_intents(parsed.get("intents")),
    }


def audio_to_flac_mono_16khz_base64(content: bytes) -> str:
    """Convert arbitrary audio bytes to mono 16 kHz FLAC and base64 encode them."""
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-sample_fmt",
        "s16",
        "-f",
        "flac",
        "pipe:1",
    ]
    try:
        result = subprocess.run(cmd, input=content, capture_output=True, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("Audio conversion to FLAC failed: ffmpeg is not installed or not available on PATH") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Audio conversion to FLAC failed: {stderr or exc}") from exc
    return base64.b64encode(result.stdout).decode("ascii")


def transcribe_audio_content(
    content: bytes,
    transcription_context: dict[str, Any] | None = None,
    *,
    model: str | None = None,
) -> dict[str, Any]:
    """Transcribe audio through the configured OpenAI-compatible gateway."""
    base64_flac = audio_to_flac_mono_16khz_base64(content)
    client = gateway_client("transcription")
    response = client.chat.completions.create(
        model=model or gateway_settings_for("transcription")[2],
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": transcription_prompt(transcription_context)},
                    {"type": "input_audio", "input_audio": {"data": base64_flac, "format": "audio/flac"}},
                ],
            }
        ],
    )
    text = response.choices[0].message.content
    if not text or not text.strip():
        raise RuntimeError("Audio transcription returned empty text")
    return parse_structured_transcription_output(text)


# --- Pro enrichment: real image captions ------------------------------------------------------
#
# Photo captioning is a Pro-tier capability (see the tier table in docs/intelligence-layer.md §3).
# The backend gates it: it attaches an `enrichmentContext` to a PHOTO worker payload only for Pro
# tenants, so a Basic tenant never incurs a gateway call and keeps a blank caption (manual add).
# The worker stays a pure function of its payload — it captions iff an `enrichmentContext` is
# present and a gateway is configured, and leaves the caption blank otherwise. The caption is a
# structured result: free-text `caption` PLUS optional attributes (out-of-context + pairing).
# Notes are NOT enriched here — they are a pure passthrough (see `run_capture_processing_job`).
#
# Worker-side downscale: vision token cost/latency scale with pixel count, so we re-encode the upload
# to a bounded-longest-edge JPEG before sending (detail:low). A product-label shot is re-read at a
# higher resolution with detail:high so the lot/brand text stays legible.

# Longest-edge caps + JPEG quality for the worker-side downscale. A normal caption pass bounds the
# longest edge into the 1024–1536 band (detail:low); a product-label re-read keeps more pixels so
# small lot/brand text is legible (detail:high). GPT-class vision tokens scale with pixels.
CAPTION_MAX_EDGE = 1280
CAPTION_PRODUCT_LABEL_MAX_EDGE = 2048
CAPTION_JPEG_QUALITY = 80
# Below this the model's own confidence is treated as "AI unsure" and the backend raises a review.
CAPTION_LOW_CONFIDENCE_THRESHOLD = 0.5
PAIRING_LATERALITIES = {"left", "right", "bilateral", "midline", "central"}
PAIRING_PHASES = {"before", "after", "during", "intraop", "other"}


def downscale_image_for_caption(
    content: bytes,
    media_type: str | None,
    *,
    max_edge: int = CAPTION_MAX_EDGE,
    quality: int = CAPTION_JPEG_QUALITY,
) -> tuple[bytes, str]:
    """Re-encode image bytes to a bounded-longest-edge JPEG before sending to the gateway.

    Honors EXIF orientation, flattens to RGB, bounds the longest edge to ``max_edge`` (keeping aspect),
    and JPEG-encodes at ``quality``. Returns ``(bytes, "image/jpeg")``. On any failure (Pillow absent,
    undecodable bytes, already small) it returns the original bytes + media type — captioning must
    never break because a downscale failed.
    """
    if Image is None or ImageOps is None:
        return content, media_type or "image/jpeg"
    try:
        with Image.open(BytesIO(content)) as image:
            image = ImageOps.exif_transpose(image)  # bake in rotation; drop EXIF
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            longest = max(image.size)
            if longest > max_edge:
                scale = max_edge / float(longest)
                image = image.resize(
                    (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                    Image.LANCZOS,
                )
            buffer = BytesIO()
            image.convert("RGB").save(buffer, format="JPEG", quality=quality, optimize=True)
            return buffer.getvalue(), "image/jpeg"
    except Exception:  # noqa: BLE001 - any decode/encode failure falls back to the raw upload
        return content, media_type or "image/jpeg"


def enrichment_language_directive(enrichment_context: dict[str, Any] | None) -> str:
    """Instruct the model on enrichment output language/script (mirrors transcription)."""
    context = enrichment_context if isinstance(enrichment_context, dict) else {}
    preferred = str(context.get("preferredLanguage") or "auto").strip().lower()
    if preferred and preferred not in {"auto", "unknown", "mixed"}:
        name = TRANSCRIPTION_LANGUAGE_NAMES.get(preferred, preferred)
        return f"Write the output in {name} using its native script. Do not translate into another language and do not romanize."
    return (
        "Write the output in the same language and script as the source material; never translate it "
        "and never romanize Persian/Farsi into Latin."
    )


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
            f"You describe photos for Memara, a clinical memory system, turning each photo into a faithful "
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


def gateway_settings_for(task: str) -> tuple[str, str, str]:
    """Resolve (base_url, api_key, model) for an AI task, falling back to the transcription gateway.

    `task` is one of `transcription`, `caption`, `patient_memory`, `report_synthesis`. A blank
    per-task override falls back to the shared `transcription_*` setting, so a single
    OpenAI-compatible gateway only needs the per-task `*_model` set, while a separate provider per
    task can also override base_url/api_key.
    """
    base_url = (getattr(settings, f"{task}_base_url", "") or settings.transcription_base_url).strip()
    api_key = getattr(settings, f"{task}_api_key", "") or settings.transcription_api_key
    model = getattr(settings, f"{task}_model", "") or settings.transcription_model
    return base_url, api_key, model


def gateway_client(task: str) -> OpenAI:
    """Return an OpenAI-compatible client for an AI task's resolved gateway."""
    base_url, api_key, _ = gateway_settings_for(task)
    return OpenAI(base_url=base_url, api_key=api_key, timeout=settings.transcription_timeout_seconds)


def resolve_model(task: str, ai_models: dict[str, Any] | None, *, override: str | None = None) -> str:
    """Resolve the model id for a task: explicit override → live `aiModels` payload → env default.

    The backend resolves the live per-task selection and passes it in the job payload's `aiModels`,
    so a model change applies to the next request; a blank/absent value falls back to the worker env.
    A task entry may be a bare model string (legacy) or a `{model, reasoningEffort}` object — the
    richer shape carries the per-task quality knobs (see `resolve_reasoning_effort`).
    """
    if isinstance(override, str) and override.strip():
        return override.strip()
    if isinstance(ai_models, dict):
        selected = ai_models.get(task)
        if isinstance(selected, dict):
            selected = selected.get("model")
        if isinstance(selected, str) and selected.strip():
            return selected.strip()
    return gateway_settings_for(task)[2]


def resolve_reasoning_effort(task: str, ai_models: dict[str, Any] | None, *, default: str | None = None) -> str | None:
    """Resolve a task's reasoning effort from the live `aiModels` payload, else `default`.

    Only the `{model, reasoningEffort}` task shape carries an effort; a bare model string has none.
    GPT-5-class models take `reasoning_effort` instead of `temperature` (which they reject), so this
    is the stability/quality knob for structured synthesis. Returns None to send no effort at all.
    """
    if isinstance(ai_models, dict):
        selected = ai_models.get(task)
        if isinstance(selected, dict):
            effort = selected.get("reasoningEffort")
            if isinstance(effort, str) and effort.strip():
                return effort.strip()
    return default


def image_to_data_url(content: bytes, media_type: str | None) -> str:
    """Base64-encode image bytes into an OpenAI-compatible data URL."""
    mime = media_type if isinstance(media_type, str) and media_type.startswith("image/") else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


# Persian (۰-۹) and Arabic-Indic (٠-٩) digits → Western/Latin 0-9. Quantification read off a photo
# (lot/batch numbers, doses, dates) must be comparable across captures regardless of the caption's
# language, so digits are normalized deterministically while the prose words stay untouched.
_LATIN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_digits_to_latin(text: str) -> str:
    """Convert Persian/Arabic-Indic digits to Western 0-9 (digit normalization, not romanizing words)."""
    return text.translate(_LATIN_DIGITS)


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


def capture_processing_output(job: dict[str, Any], text: str) -> CaptureProcessingOutput:
    """Build the stable completed-capture output envelope for a given generated text."""
    return {
        "status": "completed",
        "text": text,
        "generated_by": "ai-engine",
        "job_id": job["id"],
        "job_type": job["jobType"],
        "generated_at": utc_now().isoformat(),
        "source_artifact_ids": job.get("inputArtifactIds") or [],
    }


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


def is_fixture_capture(capture: dict[str, Any]) -> bool:
    """Return whether a capture maps to a deterministic QA fixture (skip real enrichment)."""
    metadata = capture.get("metadata") if isinstance(capture.get("metadata"), dict) else {}
    filename = str(metadata.get("original_filename") or "").strip()
    if filename in TEST_CAPTURE_TEXT_BY_FILENAME:
        return True
    detail = " ".join(str(metadata.get("detail") or "").split())
    return "Patient prefers subtle correction" in detail and "follow-up photo in 2 weeks" in detail


def raw_note_text(capture: dict[str, Any]) -> str | None:
    """Return the captured note's raw text (the passthrough's processed text), or None when empty."""
    metadata = capture.get("metadata") if isinstance(capture.get("metadata"), dict) else {}
    detail = str(metadata.get("detail") or "").strip()
    return detail or None


def completed_audio_metadata(
    job: dict[str, Any],
    capture: dict[str, Any],
    content: bytes | None,
    transcription_context: dict[str, Any] | None = None,
    *,
    model: str | None = None,
) -> CaptureProcessingOutput:
    """Return completed audio metadata using real transcription."""
    metadata = capture.get("metadata") if isinstance(capture.get("metadata"), dict) else {}
    filename = str(metadata.get("original_filename") or "").strip()
    if filename in TEST_CAPTURE_TEXT_BY_FILENAME:
        structured = structured_transcription_from_text(TEST_CAPTURE_TEXT_BY_FILENAME[filename])
    elif transcription_is_configured():
        if content is None:
            raise RuntimeError("Audio capture source file is missing")
        structured = transcribe_audio_content(content, transcription_context, model=model)
    else:
        raise RuntimeError("Audio transcription gateway is not configured")
    text = structured["transcript"]
    patient_information = structured["patient_information"]

    return {
        "status": "completed",
        "text": text,
        "language": structured["language"],
        "patient_information": patient_information,
        "clinical_summary": structured["clinical_summary"],
        "uncertainties": structured["uncertainties"],
        "intents": structured.get("intents"),
        "generated_by": "ai-engine",
        "job_id": job["id"],
        "job_type": job["jobType"],
        "generated_at": utc_now().isoformat(),
        "source_artifact_ids": job.get("inputArtifactIds") or [],
        "detected_patient": detected_patient_from_patient_information(patient_information, text),
    }


def capture_text(capture: dict[str, Any]) -> str:
    """Extract the best available mock/generated text for a capture."""
    metadata = capture.get("metadata") if isinstance(capture.get("metadata"), dict) else {}
    for key in ("transcript", "caption", "note_text", "ocr"):
        generated = metadata.get(key)
        if isinstance(generated, dict) and generated.get("text"):
            return str(generated["text"])
    filename = str(metadata.get("original_filename") or "").strip()
    if filename in TEST_CAPTURE_TEXT_BY_FILENAME:
        return TEST_CAPTURE_TEXT_BY_FILENAME[filename]
    return str(metadata.get("detail") or capture.get("type") or "capture")


def extracted_patient_information(captures: list[dict[str, Any]]) -> dict[str, Any]:
    """Return deterministic patient metadata until real extraction exists."""
    combined = "\n".join(capture_text(capture) for capture in captures)
    full_name = "Demo Patient" if "demo patient" in combined.lower() else None
    national_id = "1234567890" if "1234567890" in combined else None
    missing_fields = [
        field
        for field, value in (("full_name", full_name), ("national_id", national_id))
        if not value
    ]
    return {
        "full_name": full_name,
        "national_id": national_id,
        "expected": ["full_name", "national_id"],
        "missing_fields": missing_fields,
        "status": "complete" if not missing_fields else "missing_required",
        "source": "mock-session-job",
    }


def flattened_processing_captures(processing_context: dict[str, Any]) -> list[dict[str, Any]]:
    """Return captures from the stable session-processing input context."""
    captures = processing_context.get("captures") if isinstance(processing_context.get("captures"), dict) else {}
    flattened: list[dict[str, Any]] = []
    for group in ("audio", "photos", "text"):
        values = captures.get(group)
        if isinstance(values, list):
            flattened.extend(capture for capture in values if isinstance(capture, dict))
    return flattened


def capture_id(capture: dict[str, Any]) -> str | None:
    """Read capture IDs from either the new context or legacy worker payload."""
    value = capture.get("captureId") or capture.get("id")
    return str(value) if value else None


def session_capture_text(capture: dict[str, Any]) -> str:
    """Extract text from the session-processing context or legacy capture metadata."""
    for key in ("transcript", "caption", "rawText"):
        value = capture.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return capture_text(capture)


def extracted_patient_information_from_context(
    processing_context: dict[str, Any],
    captures: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return deterministic patient extraction without owning assignment."""
    assigned_patient = processing_context.get("assignedPatient")
    if isinstance(assigned_patient, dict):
        return {
            "status": "assigned_context_available",
            "patient_id": assigned_patient.get("patientId"),
            "display_name": assigned_patient.get("displayName"),
            "source": "db-session-assignment",
        }
    for capture in captures:
        patient_information = capture.get("patientInformation")
        if isinstance(patient_information, dict):
            meaningful_values = [
                patient_information.get("raw_mentioned_name"),
                patient_information.get("standardized_display_name"),
                patient_information.get("national_id"),
                patient_information.get("phone"),
            ]
            if any(isinstance(value, str) and value.strip() for value in meaningful_values):
                return {
                    **patient_information,
                    "source": "capture-transcription-patient-information",
                }
    return extracted_patient_information(captures)


def structured_session_report_body(
    processing_context: dict[str, Any],
    captures: list[dict[str, Any]],
    summary: str,
) -> dict[str, Any]:
    """Build deterministic body-level structured output for session processing."""
    if is_expected_test_fixture(captures):
        return expected_test_structured_report(captures, summary)

    paragraphs: list[str] = []
    history = processing_context.get("patientSummarizedHistory")
    if isinstance(history, str) and history.strip():
        paragraphs.append(f"Known patient history summary: {history.strip()}")

    audio: list[str] = []
    notes: list[str] = []
    photos: list[str] = []
    for capture in captures:
        text = session_capture_text(capture)
        if not text:
            continue
        if capture.get("type") == "audio":
            audio.append(text)
        elif capture.get("type") == "note":
            notes.append(text)
        elif capture.get("type") == "photo":
            photos.append(text)
    if audio:
        paragraphs.append("Audio notes: " + " ".join(audio))
    if notes:
        paragraphs.append("Written notes: " + " ".join(notes))
    if photos:
        paragraphs.append("Photo observations: " + " ".join(photos))
    if not paragraphs:
        paragraphs.append("Mock clinical body generated from the available session context.")

    blocks: list[dict[str, Any]] = [{"type": "paragraph", "text": paragraph} for paragraph in paragraphs]
    for capture in captures:
        if capture.get("type") == "photo" and capture.get("artifactId"):
            blocks.append(
                {
                    "type": "image",
                    "artifactId": str(capture["artifactId"]),
                    "captureId": capture_id(capture),
                    "caption": capture.get("caption") or "Source image",
                }
            )

    source_references = [{"type": "capture", "captureId": value} for value in (capture_id(capture) for capture in captures) if value]
    artifact_references = [
        {
            "type": "artifact",
            "artifactId": capture.get("artifactId"),
            "captureId": capture_id(capture),
            "url": capture.get("artifactUrl"),
            "s3Url": capture.get("s3Url"),
        }
        for capture in captures
        if capture.get("artifactId")
    ]
    return {
        "schemaVersion": "2026-05-21.session-processing-output.v1",
        "summary": summary,
        "sections": [{"id": "clinical-report", "title": "Clinical report", "blocks": blocks}],
        "artifactReferences": artifact_references,
        "sourceReferences": source_references,
        "findings": mock_findings(captures),
        "generatedBy": "mock-ai-engine",
        "generatedAt": utc_now().isoformat(),
    }


def is_expected_test_fixture(captures: list[dict[str, Any]]) -> bool:
    """Return true when uploads match the deterministic QA fixture."""
    combined = "\n".join(session_capture_text(capture) for capture in captures)
    markers = (
        "follow-up after cheek filler",
        "mild asymmetry on the left cheek",
        "0.3 mL hyaluronic acid filler",
        "avoid heavy exercise for 24 hours",
    )
    return all(marker.lower() in combined.lower() for marker in markers)


def first_capture_by_text(captures: list[dict[str, Any]], needle: str) -> dict[str, Any] | None:
    """Find a fixture capture by deterministic mock text."""
    for capture in captures:
        if needle.lower() in session_capture_text(capture).lower():
            return capture
    return None


def expected_test_structured_report(captures: list[dict[str, Any]], summary: str) -> dict[str, Any]:
    """Return the final structured report for the provided QA fixture."""
    pre_photo = first_capture_by_text(captures, "Pre-correction image")
    post_photo = first_capture_by_text(captures, "Post-correction image")
    photo_blocks: list[dict[str, Any]] = []
    for capture in (pre_photo, post_photo):
        if capture is None:
            continue
        photo_blocks.append(
            {
                "type": "image",
                "artifactId": str(capture.get("artifactId") or capture.get("sourceArtifactId") or ""),
                "captureId": capture_id(capture),
                "caption": session_capture_text(capture),
            }
        )
    source_references = [{"type": "capture", "captureId": value} for value in (capture_id(capture) for capture in captures) if value]
    artifact_references = [
        {
            "type": "artifact",
            "artifactId": capture.get("artifactId") or capture.get("sourceArtifactId"),
            "captureId": capture_id(capture),
            "url": capture.get("artifactUrl"),
            "s3Url": capture.get("s3Url"),
        }
        for capture in captures
        if capture.get("artifactId") or capture.get("sourceArtifactId")
    ]
    return {
        "schemaVersion": "2026-05-21.session-processing-output.v1",
        "summary": summary,
        "sections": [
            {
                "id": "visit-reason",
                "title": "Visit Reason",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": "Follow-up visit after cheek filler. Patient reported mild left cheek asymmetry and requested a conservative correction.",
                    }
                ],
            },
            {
                "id": "relevant-history",
                "title": "Relevant History",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": "No pain, fever, or allergy was reported during the visit. Patient prefers subtle correction and wants to avoid visible overfilling.",
                    }
                ],
            },
            {
                "id": "procedure",
                "title": "Procedure",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": "Injected 0.3 mL hyaluronic acid filler into the left mid cheek using cannula technique. Patient tolerated the procedure well.",
                    }
                ],
            },
            {"id": "photos", "title": "Photos", "blocks": photo_blocks},
            {
                "id": "aftercare",
                "title": "Aftercare",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": "Aftercare instructions were given. Patient was advised not to massage the area and to avoid heavy exercise for 24 hours. Patient should send a follow-up photo in 2 weeks if asymmetry persists.",
                    }
                ],
            },
        ],
        "artifactReferences": artifact_references,
        "sourceReferences": source_references,
        "findings": mock_findings(captures),
        "generatedBy": "mock-ai-engine",
        "generatedAt": utc_now().isoformat(),
    }


def completed_session_output(payload: dict[str, Any]) -> dict[str, Any]:
    """Return mock session summary, metadata, and report output."""
    job = payload["job"]
    session = payload["session"]
    processing_context = payload.get("sessionProcessingContext") if isinstance(payload.get("sessionProcessingContext"), dict) else {}
    captures = flattened_processing_captures(processing_context) or payload.get("captures") or []
    report_template = payload.get("reportTemplate") or {}
    captured_text = [session_capture_text(capture) for capture in captures]
    summary = (
        TEST_FINAL_SUMMARY
        if is_expected_test_fixture(captures)
        else "Mock session summary: " + (
            " ".join(text[:140] for text in captured_text[:3]) if captured_text else "No capture content was available."
        )
    )
    patient_information = extracted_patient_information_from_context(processing_context, captures)
    source_capture_ids = [capture_id(capture) for capture in captures if capture_id(capture)]
    structured_report = structured_session_report_body(processing_context, captures, summary)
    extracted_metadata = {
        "status": "completed",
        "generated_by": "ai-engine",
        "job_id": job["id"],
        "job_type": job["jobType"],
        "generated_at": utc_now().isoformat(),
        "patient_information": patient_information,
        "clinical_metadata": {
            "visit_type": "mock aesthetics consultation",
            "body_area": "mock treatment area",
            "concerns": ["mock concern"],
        },
        "source_capture_ids": source_capture_ids,
    }
    body = "\n\n".join(captured_text) if captured_text else "Mock clinical body generated from session captures."
    # The backend owns report templating and patient-information injection.
    # The AI engine returns structured clinical body content only.
    report = body
    return {
        "status": "completed",
        "summary": summary,
        "extracted_metadata": {
            **extracted_metadata,
            "progressive_report": {
                "status": "processed",
                "format": "markdown",
                "body": report,
                "source": "mock-ai-engine",
                "updated_at": utc_now().isoformat(),
            },
            "summaries": {
                "status": "processed",
                "short": summary,
                "clinical": summary,
                "source": "mock-ai-engine",
                "updated_at": utc_now().isoformat(),
            },
            "findings": mock_findings(captures),
            "processing_status": {
                "state": "complete",
                "label": "Complete",
                "stage": "complete",
                "source": "mock-ai-engine",
                "updated_at": utc_now().isoformat(),
            },
        },
        "structured_report": structured_report,
        "report": report,
        "report_template_key": report_template.get("key") or session.get("reportTemplateKey") or "default",
        "generated_by": "ai-engine",
        "job_id": job["id"],
        "generated_at": utc_now().isoformat(),
    }


def mock_findings(captures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return deterministic extracted finding rows for progressive session UX."""
    source_capture_ids = [capture_id(capture) for capture in captures if capture_id(capture)]
    if is_expected_test_fixture(captures):
        return [
            {
                "id": "procedure",
                "label": "Procedure",
                "value": "Cheek filler touch-up",
                "category": "clinical",
                "confidence": 0.96,
                "sourceCaptureIds": source_capture_ids,
                "status": "extracted",
            },
            {
                "id": "anatomical_area",
                "label": "Anatomical area",
                "value": "Left mid cheek",
                "category": "clinical",
                "confidence": 0.94,
                "sourceCaptureIds": source_capture_ids,
                "status": "extracted",
            },
            {
                "id": "product",
                "label": "Product",
                "value": "Hyaluronic acid filler",
                "category": "clinical",
                "confidence": 0.91,
                "sourceCaptureIds": source_capture_ids,
                "status": "extracted",
            },
            {
                "id": "volume",
                "label": "Volume",
                "value": "0.3 mL",
                "category": "clinical",
                "confidence": 0.96,
                "sourceCaptureIds": source_capture_ids,
                "status": "extracted",
            },
            {
                "id": "technique",
                "label": "Technique",
                "value": "Cannula technique",
                "category": "clinical",
                "confidence": 0.9,
                "sourceCaptureIds": source_capture_ids,
                "status": "extracted",
            },
            {
                "id": "aftercare",
                "label": "Aftercare",
                "value": "No massage; avoid heavy exercise for 24 hours",
                "category": "clinical",
                "confidence": 0.93,
                "sourceCaptureIds": source_capture_ids,
                "status": "extracted",
            },
        ]
    capture_types = [str(capture.get("type")) for capture in captures if capture.get("type")]
    findings = [
        {
            "id": "visit_type",
            "label": "Visit type",
            "value": "Mock aesthetics consultation",
            "category": "clinical",
            "confidence": 0.82,
            "sourceCaptureIds": source_capture_ids,
            "status": "extracted",
        },
        {
            "id": "source_mix",
            "label": "Source mix",
            "value": ", ".join(sorted(set(capture_types))) or "capture",
            "category": "session",
            "confidence": None,
            "sourceCaptureIds": source_capture_ids,
            "status": "observed",
        },
    ]
    if any("botox" in session_capture_text(capture).lower() for capture in captures):
        findings.append(
            {
                "id": "product",
                "label": "Product",
                "value": "Botox",
                "category": "clinical",
                "confidence": 0.76,
                "sourceCaptureIds": source_capture_ids,
                "status": "extracted",
            }
        )
    return findings


def session_progress_output(payload: dict[str, Any], stage: str) -> dict[str, Any]:
    """Return deterministic partial session output for one mock processing stage."""
    session = payload["session"]
    processing_context = payload.get("sessionProcessingContext") if isinstance(payload.get("sessionProcessingContext"), dict) else {}
    captures = flattened_processing_captures(processing_context) or payload.get("captures") or []
    captured_text = [session_capture_text(capture) for capture in captures]
    source_capture_ids = [capture_id(capture) for capture in captures if capture_id(capture)]
    body_source = "\n\n".join(captured_text[:2]) if captured_text else "Mock clinical body is waiting for source capture text."
    stage_copy = {
        "transcripts": "Reading source captures and preparing the report surface.",
        "report": "Drafting the clinical report from available source material.",
        "findings": "Extracting structured findings from the draft.",
        "summary": "Condensing the session into a short clinical summary.",
    }
    summary = stage_copy.get(stage, "Processing session.")
    findings = mock_findings(captures) if stage in {"findings", "summary"} else []
    return {
        "status": "processing",
        "summary": summary,
        "report_template_key": session.get("reportTemplateKey") or "default",
        "extracted_metadata": {
            "status": "processing",
            "generated_by": "ai-engine",
            "job_id": payload["job"]["id"],
            "job_type": payload["job"]["jobType"],
            "generated_at": utc_now().isoformat(),
            "source_capture_ids": source_capture_ids,
            "summaries": {
                "status": "partial",
                "short": summary,
                "clinical": summary,
                "source": "mock-ai-engine",
                "updated_at": utc_now().isoformat(),
            },
            "findings": findings,
            "processing_status": {
                "state": "processing",
                "label": summary,
                "stage": stage,
                "detail": f"Mock AI stage: {stage}",
                "source": "mock-ai-engine",
                "updated_at": utc_now().isoformat(),
            },
        },
    }


class BackendClient:
    """HTTP client for backend-owned AI job state."""

    def __init__(self) -> None:
        self.base_url = settings.backend_internal_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {settings.internal_token}"}

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST JSON to an internal backend endpoint."""
        response = httpx.post(
            f"{self.base_url}{path}",
            json=payload,
            headers=self.headers,
            timeout=settings.http_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def get_bytes(self, path: str) -> bytes:
        """GET binary content from an internal backend endpoint."""
        response = httpx.get(
            f"{self.base_url}{path}",
            headers=self.headers,
            timeout=settings.http_timeout_seconds,
        )
        response.raise_for_status()
        return response.content

    def get_file(self, path: str) -> tuple[bytes, str]:
        """GET binary content plus its content type from an internal backend endpoint."""
        response = httpx.get(
            f"{self.base_url}{path}",
            headers=self.headers,
            timeout=settings.http_timeout_seconds,
        )
        response.raise_for_status()
        return response.content, response.headers.get("content-type", "")

    def start_job(self, job_id: str, *, celery_task_id: str | None, retry_count: int) -> dict[str, Any]:
        """Mark a job running and fetch its input payload."""
        return self.post(
            f"/internal/ai/jobs/{job_id}/start",
            {"celery_task_id": celery_task_id, "retry_count": retry_count},
        )

    def complete_job(self, job_id: str, *, output_key: str, output: dict[str, Any]) -> dict[str, Any]:
        """Submit successful job output to the backend."""
        return self.post(
            f"/internal/ai/jobs/{job_id}/complete",
            {"output_key": output_key, "output": output},
        )

    def progress_job(self, job_id: str, *, output_key: str, output: dict[str, Any], stage: str) -> dict[str, Any]:
        """Submit partial job output to the backend."""
        return self.post(
            f"/internal/ai/jobs/{job_id}/progress",
            {"output_key": output_key, "output": output, "stage": stage},
        )

    def retry_job(
        self,
        job_id: str,
        *,
        error_message: str,
        celery_task_id: str | None,
        retry_count: int,
        retry_reason: str | None = None,
    ) -> dict[str, Any]:
        """Record a failed attempt before Celery retries."""
        return self.post(
            f"/internal/ai/jobs/{job_id}/retry",
            {
                "error_message": error_message,
                "celery_task_id": celery_task_id,
                "retry_count": retry_count,
                "retry_reason": retry_reason,
            },
        )

    def fail_job(
        self,
        job_id: str,
        *,
        error_message: str,
        celery_task_id: str | None,
        retry_count: int,
        retry_reason: str | None = None,
    ) -> dict[str, Any]:
        """Record terminal job failure."""
        return self.post(
            f"/internal/ai/jobs/{job_id}/fail",
            {
                "error_message": error_message,
                "celery_task_id": celery_task_id,
                "retry_count": retry_count,
                "retry_reason": retry_reason,
            },
        )

    def recover_jobs(self) -> dict[str, Any]:
        """Ask the backend to re-dispatch queued or retryable failed work."""
        return self.post("/internal/ai/jobs/recover", {})


def run_capture_processing_job(job_id: str, *, celery_task_id: str | None, retry_count: int) -> None:
    """Run a capture processing job through the backend API contract."""
    client = BackendClient()
    payload = client.start_job(job_id, celery_task_id=celery_task_id, retry_count=retry_count)
    job = payload["job"]
    capture = payload["capture"]
    if job.get("status") == "succeeded":
        return

    output_key = output_key_for_capture(capture["type"])
    ai_models = payload.get("aiModels") if isinstance(payload.get("aiModels"), dict) else None
    # Audio transcription and Pro photo/note enrichment are real (gateway-backed); Basic, gateway-less,
    # and QA-fixture captures fall back to the deterministic placeholder below.
    client.progress_job(job_id, output_key=output_key, output=partial_metadata(job, capture), stage="transcript")
    if capture.get("type") == "audio":
        source_content = None
        if transcription_is_configured() and capture.get("sourceArtifactId"):
            source_content = client.get_bytes(f"/internal/captures/{capture['id']}/file-content")
        if not transcription_is_configured():
            sleep(settings.mock_stage_delay_seconds)
        client.complete_job(
            job_id,
            output_key=output_key,
            output=completed_audio_metadata(
                job,
                capture,
                source_content,
                payload.get("transcriptionContext"),
                model=resolve_model("transcription", ai_models),
            ),
        )
        return

    # Notes are a pure passthrough (note decoration removed): no gateway call ever. The job marks the
    # note processed with its RAW text — preserving chain ordering + report_contribution wiring — and
    # the report reads the raw `detail`. Fixtures keep their deterministic text for QA.
    if capture.get("type") == "note" and not is_fixture_capture(capture):
        client.complete_job(job_id, output_key=output_key, output=capture_processing_output(job, raw_note_text(capture) or ""))
        return

    # Pro photo captioning. The backend attaches an `enrichmentContext` only for Pro tenants; Basic and
    # gateway-less/fixture captures keep the deterministic/blank fallback. A gateway failure propagates
    # as a retryable worker error; an empty gateway response leaves the caption blank (manual add).
    enrichment_context = payload.get("enrichmentContext") if isinstance(payload.get("enrichmentContext"), dict) else None
    if (
        capture.get("type") == "photo"
        and enrichment_context is not None
        and transcription_is_configured()
        and not is_fixture_capture(capture)
        and capture.get("sourceArtifactId")
    ):
        content, media_type = client.get_file(f"/internal/captures/{capture['id']}/file-content")
        caption_result = caption_image_content(
            content, media_type, enrichment_context, model=resolve_model("caption", ai_models)
        )
        output = caption_output_metadata(job, caption_result) if caption_result else capture_processing_output(job, "")
        client.complete_job(job_id, output_key=output_key, output=output)
        return

    # Un-enriched photos (Basic tenants, or no gateway) get NO AI caption — leave it blank so the UI
    # offers a manual "Add caption" instead of a meaningless placeholder. Fixtures keep their
    # deterministic caption for QA.
    if capture.get("type") == "photo" and not is_fixture_capture(capture):
        client.complete_job(job_id, output_key=output_key, output=capture_processing_output(job, ""))
        return

    sleep(settings.mock_stage_delay_seconds)
    client.complete_job(job_id, output_key=output_key, output=completed_metadata(job, capture))


# --- Session report synthesis + treatment extraction (Pro, single-pass) ------------------------
#
# The keystone of the Pro capture-intelligence wave. ONE structured call emits the per-visit report
# sections AND the performed treatments[] together (the A↔B contract). It is dispatched by the
# backend (the revived `session_organize` job) only for Pro tenants with a gateway, AFTER the
# deterministic baseline already wrote a report — so synthesis is a refinement that never blocks the
# capture. Gateway-less / malformed → a SKIP sentinel; the backend keeps the deterministic baseline
# and treatments stay empty (Basic + gateway-less run zero AI and must never break).

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


def report_synthesis_json_schema() -> dict[str, Any]:
    """JSON schema for the single-pass synthesis structured output (the A↔B contract)."""
    block = {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["paragraph", "image"]},
            "text": {"type": ["string", "null"]},
            "captureId": {"type": ["string", "null"]},
            "caption": {"type": ["string", "null"]},
        },
        "required": ["type"],
    }
    section = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "title": {"type": "string"},
            "blocks": {"type": "array", "items": block},
        },
        "required": ["id", "title", "blocks"],
    }
    treatment = {
        "type": "object",
        "properties": {
            "area": {"type": "string"},
            "product": {"type": "string"},
            "brand": {"type": ["string", "null"]},
            "quantity": {"type": ["number", "null"]},
            "unit": {"type": ["string", "null"]},
            "quantityText": {"type": ["string", "null"]},
            "lot": {"type": ["string", "null"]},
            "confidence": {"type": "number"},
            "sourceCaptureIds": {"type": "array", "items": {"type": "string"}},
            "evidence": {"type": ["string", "null"]},
            "carriedForward": {"type": "boolean"},
            "supersedesCaptureId": {"type": ["string", "null"]},
            "attributes": {"type": "object"},
        },
        "required": ["area", "product", "confidence", "sourceCaptureIds", "carriedForward"],
    }
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "language": {"type": "string", "enum": ["fa", "en", "mixed"]},
            "sections": {"type": "array", "items": section},
            "treatments": {"type": "array", "items": treatment},
            "uncertainties": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary", "language", "sections", "treatments", "uncertainties"],
    }


def report_synthesis_prompt(processing_context: dict[str, Any]) -> str:
    """Build the single-pass report-synthesis + treatment-extraction prompt.

    Vertical-AGNOSTIC: the clinical setting comes from the domain descriptor (neutral "clinic" when
    absent). The prompt encodes the design's discipline: ground every statement in captures, native
    script prose, verbatim quantities/brands, stable targeted update from the prior draft + changeset,
    corrections-vs-additions with `supersedesCaptureId`, carry-forward only on an explicit cue, and
    "leave null rather than guess".
    """
    context = processing_context if isinstance(processing_context, dict) else {}
    label, vocabulary, _ = domain_framing(context)
    report_language = context.get("reportLanguage")
    language_directive = (
        f"Write all report prose in {report_language} using its native script."
        if isinstance(report_language, str) and report_language.strip()
        else "Write all report prose in the language the captures use (the report template's default)."
    )
    vocab_line = f"Common {label} vocabulary may include {', '.join(vocabulary)}. " if vocabulary else ""
    section_lines = "; ".join(f"{section_id} ({title})" for section_id, title in SYNTHESIS_SECTIONS)
    return "\n\n".join(
        (
            f"You are Memara, synthesizing ONE per-visit clinical report and extracting the performed "
            f"treatments for a {label}. Work only from the provided captures (audio transcripts, photo "
            f"captions, and raw text notes) and the prior visit context. Invent nothing.",
            (
                "Produce a strict JSON object with EXACTLY these keys: summary, language, sections, "
                "treatments, uncertainties.\n"
                f"- sections: populate these fixed section ids, in this order: {section_lines}. Each "
                "section has id, title, and blocks. A block is either {\"type\":\"paragraph\",\"text\":...} "
                "or {\"type\":\"image\",\"captureId\":<a photo captureId from the context>,\"caption\":...}. "
                "Leave a section's blocks empty ([]) when the captures do not support it — never pad it.\n"
                f"- {language_directive} Write the DESCRIPTIVE treatment fields — area, product (the "
                "generic/category, e.g. فیلر/ژل, بوتاکس), and unit (e.g. واحد, سی‌سی) — in the REPORT "
                "LANGUAGE using its native script; prefer the clinician's own word when they gave one. "
                "Do NOT emit an English category (\"filler\", \"botox\", \"unit\") in a Persian report. "
                "Keep VERBATIM in their original script: brand names, lot numbers, patient/clinician "
                "quotes, and quantityText (e.g. «۲ سی‌سی») — never translate or romanize these, and never "
                "normalize «۲» to \"2\" in quantityText.\n"
                f"{vocab_line}"
                "- treatments: one TreatmentItem per distinct performed treatment, with core fields "
                "area, product, brand, quantity (number or null), unit, quantityText (VERBATIM original "
                "script), lot (dictated or read off a product-label photo), confidence (0..1), "
                "sourceCaptureIds, evidence, carriedForward, supersedesCaptureId, and an open attributes "
                "map (needleGauge, depth, device, sessions, …). The treatment-performed section is a prose "
                "MIRROR of treatments — keep them consistent.\n"
                "- Leave any field null rather than guessing. Set confidence to reflect genuine certainty."
            ),
            (
                "UPDATE DISCIPLINE — the captures are authoritative. If a prior report draft and a "
                "changeset are provided, update the prior draft to match the current captures: keep "
                "unchanged prose byte-stable, recompute only the sections/treatments affected by the "
                "changed captures, and REMOVE anything no longer supported by a capture."
            ),
            (
                "CORRECTIONS vs ADDITIONS (e.g. «ژل ۲ سی‌سی» then «ژل ۳ سی‌سی» for the same area):\n"
                "- CORRECTION (supersede): on an explicit correction cue (اشتباه گفتم، منظورم…بود، "
                "\"actually\", \"make that\") OR the same area+product+unit simply restated with a new "
                "quantity. Emit ONE corrected TreatmentItem and set supersedesCaptureId to the captureId "
                "of the superseded statement (auditable/undoable).\n"
                "- ADDITION: on an additive cue (هم…هم، اضافه، \"another\") OR a different area/product. "
                "Emit a separate TreatmentItem for each.\n"
                "- AMBIGUOUS (cannot tell correction from addition): DO NOT silently overwrite. Emit BOTH "
                "treatments AND add a clear sentence to uncertainties describing the ambiguity."
            ),
            (
                "CARRY-FORWARD: only when a capture explicitly says \"same as last time\" (همون قبلی، "
                "مثل دفعه قبل). Then set carriedForward=true, LOWER the confidence, cite the prior visit "
                "in sourceCaptureIds/evidence, and copy the referenced prior-visit treatment. NEVER "
                "silently materialize a prior dose without an explicit cue."
            ),
            (
                "uncertainties: a list of short human-readable sentences for anything a clinician should "
                "confirm (ambiguous correction, a missing-but-expected lot number, a low-confidence "
                "product, a carried-forward dose). Return ONLY strict JSON, no markdown, no code fences."
            ),
            f"Session context (captures, prior report draft, changeset, prior-visit treatments):\n{json.dumps(context, ensure_ascii=False, sort_keys=True)}",
        )
    )


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
    return {
        "area": _text(area) or "",
        "product": _text(product) or "",
        "brand": _text(raw.get("brand")),
        "quantity": _number(raw.get("quantity")),
        "unit": _text(raw.get("unit")),
        "quantityText": _text(raw.get("quantityText")),
        "lot": _text(raw.get("lot")),
        "confidence": clamp_confidence(raw.get("confidence")),
        "sourceCaptureIds": [str(value) for value in source_ids if isinstance(value, str)] if isinstance(source_ids, list) else [],
        "evidence": _text(raw.get("evidence")),
        "carriedForward": raw.get("carriedForward") is True,
        "supersedesCaptureId": _text(raw.get("supersedesCaptureId")),
        "attributes": attributes if isinstance(attributes, dict) else {},
    }


def parse_session_synthesis_output(raw_text: str, *, source_capture_ids: list[str] | None = None) -> dict[str, Any] | None:
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
        {"id": section_id, "title": title, "blocks": blocks_by_id.get(section_id, [])}
        for section_id, title in SYNTHESIS_SECTIONS
    ]

    treatments = [cleaned for cleaned in (_clean_synthesis_treatment(item) for item in (parsed.get("treatments") or [])) if cleaned]
    language = parsed.get("language") if parsed.get("language") in SYNTHESIS_LANGUAGES else "mixed"
    uncertainties = parsed.get("uncertainties")
    source_references = [{"type": "capture", "captureId": capture_id} for capture_id in (source_capture_ids or [])]
    return {
        "schemaVersion": SESSION_SYNTHESIS_OUTPUT_VERSION,
        "summary": summary.strip(),
        "language": language,
        "sections": sections,
        "treatments": treatments,
        "sourceReferences": source_references,
        "uncertainties": [str(value) for value in uncertainties if isinstance(value, str)] if isinstance(uncertainties, list) else [],
        "generatedBy": "ai-engine",
        "generatedAt": utc_now().isoformat(),
    }


def synthesize_session_report(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Run the single-pass report synthesis through the gateway; None to fall back to baseline.

    Network/gateway EXCEPTIONS propagate (retryable). Empty/malformed CONTENT returns None so the
    caller emits the skip sentinel and the deterministic baseline stands (never breaks).
    """
    processing_context = payload.get("sessionProcessingContext") if isinstance(payload.get("sessionProcessingContext"), dict) else {}
    captures = flattened_processing_captures(processing_context)
    source_capture_ids = [capture_id(capture) for capture in captures if capture_id(capture)]
    ai_models = payload.get("aiModels") if isinstance(payload.get("aiModels"), dict) else None
    model = resolve_model("report_synthesis", ai_models)
    effort = resolve_reasoning_effort(
        "report_synthesis", ai_models, default=(settings.report_synthesis_reasoning_effort or None)
    )
    client = gateway_client("report_synthesis")
    request: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": report_synthesis_prompt(processing_context)}],
        # Schema-enforced JSON; NO temperature (GPT-5-class rejects it — stability from low effort).
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "session_synthesis_output", "schema": report_synthesis_json_schema()},
        },
    }
    if effort:
        request["extra_body"] = {"reasoning_effort": effort}
    response = client.chat.completions.create(**request)
    return parse_session_synthesis_output(response.choices[0].message.content or "", source_capture_ids=source_capture_ids)


def session_synthesis_skip_output(reason: str) -> dict[str, Any]:
    """Sentinel telling the backend synthesis did not run — keep the deterministic baseline."""
    return {
        "status": "skipped",
        "synthesis_skipped": True,
        "reason": reason,
        "generated_by": "ai-engine",
        "generated_at": utc_now().isoformat(),
    }


def completed_session_synthesis_output(payload: dict[str, Any]) -> dict[str, Any]:
    """Build the worker completion envelope for a Pro session synthesis job.

    Wraps the A↔B synthesis output as `structured_report` plus the top-level summary +
    extracted_metadata the backend's `complete_session_worker_job` expects. Gateway-less or
    malformed → a skip sentinel so the deterministic baseline is preserved (treatments empty).
    """
    job = payload["job"]
    session = payload.get("session") if isinstance(payload.get("session"), dict) else {}
    report_template = payload.get("reportTemplate") if isinstance(payload.get("reportTemplate"), dict) else {}
    if not transcription_is_configured():
        return session_synthesis_skip_output("gateway_not_configured")
    synthesis = synthesize_session_report(payload)
    if synthesis is None:
        return session_synthesis_skip_output("empty_or_malformed_synthesis")

    source_capture_ids = [reference["captureId"] for reference in synthesis["sourceReferences"] if reference.get("captureId")]
    extracted_metadata = {
        "status": "completed",
        "generated_by": "ai-engine",
        "job_id": job["id"],
        "job_type": job["jobType"],
        "generated_at": utc_now().isoformat(),
        "source_capture_ids": source_capture_ids,
        # The backend post-processes treatments (validate/supersede/carry-forward) before storing.
        "treatments": synthesis["treatments"],
        "uncertainties": synthesis["uncertainties"],
        "processing_status": {
            "state": "complete",
            "label": "Complete",
            "stage": "complete",
            "source": "ai-engine",
            "updated_at": utc_now().isoformat(),
        },
    }
    return {
        "status": "completed",
        "summary": synthesis["summary"],
        "structured_report": synthesis,
        "extracted_metadata": extracted_metadata,
        "report_template_key": report_template.get("key") or session.get("reportTemplateKey") or "default",
        "generated_by": "ai-engine",
        "job_id": job["id"],
        "generated_at": utc_now().isoformat(),
    }


def run_session_processing_job(job_id: str, *, celery_task_id: str | None, retry_count: int) -> None:
    """Run a session processing job through the backend API contract."""
    client = BackendClient()
    payload = client.start_job(job_id, celery_task_id=celery_task_id, retry_count=retry_count)
    job = payload["job"]
    if job.get("status") == "succeeded":
        return

    # Pro single-pass report synthesis + treatment extraction (the revived `session_organize`). The
    # backend sets `reportSynthesis` only for Pro tenants with a gateway, AFTER the deterministic
    # baseline already wrote a report. Gateway-less / malformed yields a skip sentinel that the
    # backend treats as "keep the deterministic baseline" (treatments empty) — never breaks.
    if payload.get("reportSynthesis"):
        client.complete_job(job_id, output_key="session_outputs", output=completed_session_synthesis_output(payload))
        return

    # Legacy deterministic progressive stages (placeholder pipeline + recovery of pre-synthesis jobs).
    for stage in ("transcripts", "report", "findings", "summary"):
        client.progress_job(job_id, output_key="session_progress", output=session_progress_output(payload, stage), stage=stage)
        sleep(settings.mock_stage_delay_seconds)

    client.complete_job(job_id, output_key="session_outputs", output=completed_session_output(payload))


# --- Combined patient memory (Pro): summary + history in one call ------------------------------


def patient_memory_prompt(payload: dict[str, Any]) -> str:
    """Build the prompt for the combined patient summary + history (incremental, grounded)."""
    patient = payload.get("patient") if isinstance(payload.get("patient"), dict) else {}
    language = payload.get("language")
    label, _, _ = domain_framing(payload)  # vertical-aware; neutral "clinic" when absent
    language_directive = (
        f"Write EVERY field in {language} and ONLY {language} — one language throughout, native script."
        if isinstance(language, str) and language.strip()
        else (
            "Write EVERY field in the SAME language the visit notes use (if the notes are Persian/Farsi, "
            "write Persian — do NOT default to English) — one language throughout, native script."
        )
    )
    return "\n\n".join(
        (
            "You are Memara, a calm clinical assistant that maintains a patient's longitudinal memory. "
            f"The clinical setting is a {label}.",
            (
                "Update this patient's memory from the prior memory and the new visit briefs below. "
                "Each visit brief may include the treatments performed that visit (product, dose, area, "
                "lot) — use them to ground recall in specifics (e.g. 'last visit: Voluma 0.3 mL, left "
                "cheek'), quoting doses verbatim. Produce a warm, assistant-voiced brief — natural "
                "sentences, never a form or bullet dump. Synthesize across visits, but do NOT invent "
                "clinical facts, names, products, or doses that are not present in the briefs. Do NOT "
                "include the patient's name in any field — it is already shown beside this text in the "
                "UI; use pronouns or omit the subject. Keep the card summary to 1-2 sentences. "
                "Also produce a compact 'card' for the line-up worklist: 'storySoFar' and 'rightNow' are "
                "EACH at most 2 short sentences; 'flags' surfaces only genuinely important "
                "allergy/consent/preference/caution items actually found in the briefs — return an empty "
                "list when there are none, and never invent one. "
                f"{language_directive} "
                "The whole brief MUST be in that one language — NEVER mix (e.g. an English sentence "
                "containing «گونه چپ»). Brand names and lot numbers may keep their original form. When "
                "the language is Persian/Farsi, embedding common English clinical terms is fine "
                "(Finglish, e.g. «فیلر گونه چپ»), but do not switch into English sentences and never "
                "romanize Persian into Latin."
            ),
            (
                "Return ONLY strict JSON (no markdown, no code fences) with EXACTLY this shape:\n"
                '{"summary": "<1-2 sentence card summary>", '
                '"history": {"snapshot": "<one line: patient + current focus>", '
                '"sections": [{"label": "Story so far", "body": "<2-4 sentences>"}, '
                '{"label": "Worth remembering", "body": "<preferences, cautions, recurring themes>"}, '
                '{"label": "Right now", "body": "<open threads / next visit>"}], "visits": []}, '
                '"card": {"storySoFar": "<at most 2 short sentences>", '
                '"rightNow": "<at most 2 short sentences: what is open / next visit>", '
                '"flags": [{"kind": "allergy|consent|preference|caution", "label": "<short>"}]}}'
            ),
            f"Patient context:\n{json.dumps(patient, ensure_ascii=False, sort_keys=True)}",
        )
    )


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
    return {"summary": summary.strip(), "history": history, "card": card if isinstance(card, dict) else None}


def completed_patient_memory_output(payload: dict[str, Any]) -> dict[str, Any]:
    """Build the combined patient summary+history output, via the gateway when configured.

    Falls back to the backend-provided deterministic content when no gateway is configured or when
    the model returns something unusable, so the job always completes with valid memory.
    """
    fallback = payload.get("deterministicFallback") if isinstance(payload.get("deterministicFallback"), dict) else {}

    def _fallback_output() -> dict[str, Any]:
        return {
            "summary": fallback.get("summary"),
            "history": fallback.get("history"),
            "card": fallback.get("card"),
            "source": fallback.get("source") or "mock-deterministic",
            "generated_by": "ai-engine",
            "generated_at": utc_now().isoformat(),
        }

    if not transcription_is_configured():
        return _fallback_output()

    ai_models = payload.get("aiModels") if isinstance(payload.get("aiModels"), dict) else None
    model = resolve_model("patient_memory", ai_models)
    client = gateway_client("patient_memory")
    # A gateway/network error propagates and is retried by the task wrapper (gateway_unavailable).
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": patient_memory_prompt(payload)}],
    )
    parsed = parse_patient_memory_output(response.choices[0].message.content or "")
    if parsed is None:
        return _fallback_output()
    history = parsed["history"]
    history["source"] = f"ai:{model}"
    return {
        "summary": parsed["summary"],
        "history": history,
        # Carry the model's compact card through; backend coerces it + falls back deterministically.
        "card": parsed.get("card") or fallback.get("card"),
        "source": f"ai:{model}",
        "model": model,
        "generated_by": "ai-engine",
        "generated_at": utc_now().isoformat(),
    }


def run_patient_memory_job(job_id: str, *, celery_task_id: str | None, retry_count: int) -> None:
    """Run a combined patient summary+history job through the backend API contract."""
    client = BackendClient()
    payload = client.start_job(job_id, celery_task_id=celery_task_id, retry_count=retry_count)
    job = payload["job"]
    if job.get("status") == "succeeded":
        return
    client.complete_job(job_id, output_key="patient_memory", output=completed_patient_memory_output(payload))


def qa_draft_prompt(payload: dict[str, Any]) -> str:
    """Build the prompt for a post-session patient Q&A reply draft (AES-402).

    The doctor reviews and approves the result before anything is sent, so the draft must be a warm,
    clinically-cautious *suggestion* grounded in the doctor's prior answers + this patient's context,
    inventing no clinical facts and escalating to the clinic when warranted.
    """
    qa = payload.get("qaDraft") if isinstance(payload.get("qaDraft"), dict) else {}
    return "\n\n".join(
        (
            "You are Memara, drafting a reply on behalf of an aesthetics clinic doctor to a patient's "
            "between-visits question. The doctor will review and edit before sending.",
            (
                "Write a warm, concise reply (2-4 sentences) in the patient's voice-appropriate register. "
                "Ground it in the doctor's PRIOR ANSWERS and THIS PATIENT'S CONTEXT below; match the "
                "doctor's tone. Do NOT invent clinical facts, doses, products, or diagnoses not present "
                "in the context. Reassure when appropriate, reference the aftercare already given, and "
                "tell the patient to contact the clinic if symptoms worsen or they are worried. Sign off "
                f"as {qa.get('doctorName') or 'the clinic'}. Return ONLY the plain-text reply."
            ),
            f"Patient question:\n{qa.get('patientQuestion', '')}",
            f"This patient's context:\n{json.dumps(qa.get('patientContext', {}), ensure_ascii=False, sort_keys=True)}",
            f"The doctor's prior answers:\n{json.dumps(qa.get('priorAnswers', []), ensure_ascii=False, sort_keys=True)}",
        )
    )


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


def completed_qa_draft_output(payload: dict[str, Any]) -> dict[str, Any]:
    """Build the Q&A reply-draft output, via the gateway when configured.

    Falls back to the backend-provided deterministic draft when no gateway is configured or the
    model returns nothing usable, so the job always completes and the inbox always has a suggestion.
    """
    fallback = payload.get("deterministicFallback") if isinstance(payload.get("deterministicFallback"), dict) else {}

    def _fallback_output() -> dict[str, Any]:
        return {
            "draft": fallback.get("draft"),
            "source": fallback.get("source") or "mock-deterministic",
            "generated_by": "ai-engine",
            "generated_at": utc_now().isoformat(),
        }

    if not transcription_is_configured():
        return _fallback_output()

    ai_models = payload.get("aiModels") if isinstance(payload.get("aiModels"), dict) else None
    model = resolve_model("qa_draft", ai_models)
    client = gateway_client("qa_draft")
    # A gateway/network error propagates and is retried by the task wrapper (gateway_unavailable).
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": qa_draft_prompt(payload)}],
    )
    draft = parse_qa_draft_output(response.choices[0].message.content or "")
    if draft is None:
        return _fallback_output()
    return {
        "draft": draft,
        "source": f"ai:{model}",
        "model": model,
        "generated_by": "ai-engine",
        "generated_at": utc_now().isoformat(),
    }


def run_qa_draft_job(job_id: str, *, celery_task_id: str | None, retry_count: int) -> None:
    """Run a post-session patient Q&A reply-draft job through the backend API contract (AES-402)."""
    client = BackendClient()
    payload = client.start_job(job_id, celery_task_id=celery_task_id, retry_count=retry_count)
    job = payload["job"]
    if job.get("status") == "succeeded":
        return
    client.complete_job(job_id, output_key="qa_draft", output=completed_qa_draft_output(payload))


def qa_revise_prompt(payload: dict[str, Any]) -> str:
    """Prompt for a Q&A reply voice edit: classify revise-vs-replace and produce the reply (AES-402).

    The doctor recorded a voice note while reviewing a draft reply. The model must decide whether the
    note is a *revision* of the current draft or an *entirely new reply*, then output the resulting
    reply. The doctor approves before anything is sent, so this is a suggestion — invent no clinical
    facts beyond the draft + spoken note + context.
    """
    qa = payload.get("qaRevise") if isinstance(payload.get("qaRevise"), dict) else {}
    return "\n\n".join(
        (
            "You are Memara, helping an aesthetics-clinic doctor edit a reply to a patient's question "
            "using a voice note they just recorded. The doctor reviews and approves before sending.",
            (
                "Decide from the VOICE NOTE whether the doctor is REVISING the current draft (e.g. "
                "'make it warmer', 'remove the part about ice', 'add that she should avoid sun') or "
                "dictating an ENTIRELY NEW reply. Then produce the final reply text in the patient's "
                "language. Keep the doctor's sign-off. Do NOT invent clinical facts, doses, or products "
                "not present in the current draft, the spoken note, or the context. "
                "Return STRICT JSON only: {\"mode\":\"revise\"|\"replace\",\"reply\":\"<final reply text>\"}."
            ),
            f"Patient question:\n{qa.get('patientQuestion', '')}",
            f"Current draft reply:\n{qa.get('currentDraft', '')}",
            f"This patient's context:\n{json.dumps(qa.get('patientContext', {}), ensure_ascii=False, sort_keys=True)}",
            f"The doctor's prior answers:\n{json.dumps(qa.get('priorAnswers', []), ensure_ascii=False, sort_keys=True)}",
        )
    )


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
    mode = parsed.get("mode") if parsed.get("mode") in {"revise", "replace"} else "revise"
    return {"mode": mode, "reply": reply.strip()}


def completed_qa_revise_output(payload: dict[str, Any], audio: bytes) -> dict[str, Any]:
    """Revise/replace the reply from the doctor's voice note via the configured Q&A model.

    Falls back to keeping the current draft unchanged when no gateway is configured or the model
    returns nothing usable, so the job always completes (the doctor can still edit by hand).
    """
    fallback = payload.get("deterministicFallback") if isinstance(payload.get("deterministicFallback"), dict) else {}

    def _fallback_output() -> dict[str, Any]:
        return {
            "mode": fallback.get("mode") or "revise",
            "reply": fallback.get("reply"),
            "source": fallback.get("source") or "mock-deterministic",
            "generated_by": "ai-engine",
            "generated_at": utc_now().isoformat(),
        }

    if not transcription_is_configured() or not audio:
        return _fallback_output()

    ai_models = payload.get("aiModels") if isinstance(payload.get("aiModels"), dict) else None
    model = resolve_model("qa_draft", ai_models)
    base64_flac = audio_to_flac_mono_16khz_base64(audio)
    client = gateway_client("qa_draft")
    # A gateway/network error propagates and is retried by the task wrapper.
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": qa_revise_prompt(payload)},
                    {"type": "input_audio", "input_audio": {"data": base64_flac, "format": "audio/flac"}},
                ],
            }
        ],
    )
    parsed = parse_qa_revise_output(response.choices[0].message.content or "")
    if parsed is None:
        return _fallback_output()
    return {
        "mode": parsed["mode"],
        "reply": parsed["reply"],
        "source": f"ai:{model}",
        "model": model,
        "generated_by": "ai-engine",
        "generated_at": utc_now().isoformat(),
    }


def run_qa_revise_job(job_id: str, *, celery_task_id: str | None, retry_count: int) -> None:
    """Run a Q&A reply voice-edit job (revise/replace from the doctor's spoken note; AES-402)."""
    client = BackendClient()
    payload = client.start_job(job_id, celery_task_id=celery_task_id, retry_count=retry_count)
    job = payload["job"]
    if job.get("status") == "succeeded":
        return
    qa = payload.get("qaRevise") if isinstance(payload.get("qaRevise"), dict) else {}
    audio = b""
    endpoint = qa.get("voiceEndpoint")
    if transcription_is_configured() and endpoint:
        audio, _ = client.get_file(endpoint)
    client.complete_job(job_id, output_key="qa_revise", output=completed_qa_revise_output(payload, audio))
