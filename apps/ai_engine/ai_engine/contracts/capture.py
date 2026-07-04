"""Capture-intelligence contracts: structured transcription + patient information + intents.

The audio capture job emits a transcript (required, high-trust) plus best-effort patient identity and
intent classification. Intents are optional and dropped field-by-field on malformation so a bad intent
payload never invalidates a usable transcript — that tolerance is the contract and is preserved here.
"""
from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_engine.core.errors import InvalidOutput
from ai_engine.core.text import normalize_digits_to_latin
from ai_engine.core.util import clamp_confidence

# Documented schema id for the capture-intelligence envelope — now code, not prose.
CAPTURE_INTELLIGENCE_OUTPUT_VERSION = "2026-06-03.capture-intelligence.v1"

TRANSCRIPTION_LANGUAGES = {"fa", "en", "mixed", "unknown"}
ASSIGNMENT_INTENT_BASES = {"explicit", "implicit"}
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


class PatientInformation(BaseModel):
    """Identity details extracted from a single capture (all optional; confidence defaults to 0)."""

    model_config = ConfigDict(extra="ignore")

    raw_mentioned_name: str | None = None
    standardized_display_name: str | None = None
    alternate_transliterations: list[str] = Field(default_factory=list)
    national_id: str | None = None
    phone: str | None = None
    date_of_birth: str | None = None
    evidence: str | None = None
    confidence: float = 0.0
    source_text: str | None = None


class AssignmentIntent(BaseModel):
    """A stated/mentioned patient assignment for this visit (explicit correction vs implicit statement)."""

    present: Literal[True] = True
    basis: str
    confidence: float
    evidence: str | None = None


class AppendIntent(BaseModel):
    """The capture only adds incremental detail to an ongoing note."""

    present: Literal[True] = True
    confidence: float


class OutOfContextIntent(BaseModel):
    """The capture has no clinical/visit content."""

    present: Literal[True] = True
    confidence: float
    reason: str | None = None


class StructuredTranscription(BaseModel):
    """The validated audio-capture output: transcript + identity + optional intents."""

    model_config = ConfigDict(extra="ignore")

    transcript: str
    language: str
    patient_information: PatientInformation
    clinical_summary: str | None = None
    uncertainties: list[str] = Field(default_factory=list)
    intents: dict[str, Any] | None = None


def transcription_json_schema() -> dict[str, Any]:
    """Gateway ``json_schema`` for the structured transcription output (§3.2). Loose, mirrors the prompt."""
    intent = lambda extra: {"type": ["object", "null"], "properties": {"present": {"type": "boolean"}, **extra}}
    return {
        "type": "object",
        "properties": {
            "transcript": {"type": "string"},
            "language": {"type": "string", "enum": ["fa", "en", "mixed", "unknown"]},
            "patient_information": {
                "type": "object",
                "properties": {
                    "raw_mentioned_name": {"type": ["string", "null"]},
                    "standardized_display_name": {"type": ["string", "null"]},
                    "alternate_transliterations": {"type": "array", "items": {"type": "string"}},
                    "national_id": {"type": ["string", "null"]},
                    "phone": {"type": ["string", "null"]},
                    "date_of_birth": {"type": ["string", "null"]},
                    "evidence": {"type": ["string", "null"]},
                    "confidence": {"type": "number"},
                },
            },
            "clinical_summary": {"type": ["string", "null"]},
            "uncertainties": {"type": "array", "items": {"type": "string"}},
            "intents": {
                "type": ["object", "null"],
                "properties": {
                    "assignment": intent({"basis": {"type": ["string", "null"]}, "confidence": {"type": "number"}, "evidence": {"type": ["string", "null"]}}),
                    "append": intent({"confidence": {"type": "number"}}),
                    "out_of_context": intent({"confidence": {"type": "number"}, "reason": {"type": ["string", "null"]}}),
                },
            },
        },
        "required": ["transcript", "language", "patient_information"],
    }


def empty_patient_information(*, source_text: str | None = None) -> dict[str, Any]:
    """Return the patient-information dict for no detected identity."""
    return PatientInformation(source_text=source_text).model_dump()


def structured_transcription_from_text(text: str, *, language: str = "en") -> dict[str, Any]:
    """Return deterministic structured transcription for fixtures and fallback output."""
    return StructuredTranscription(
        transcript=text,
        language=language,
        patient_information=PatientInformation(source_text=text),
        clinical_summary=None,
        uncertainties=[],
        intents=None,
    ).model_dump()


def normalize_intents(raw: Any) -> dict[str, Any] | None:
    """Normalize best-effort intent classification, dropping absent or malformed intents.

    The transcript is the required, high-trust field; intents are optional so a malformed intent
    payload never invalidates an otherwise usable transcript.
    """
    if not isinstance(raw, dict):
        return None
    intents: dict[str, Any] = {}
    assignment = raw.get("assignment")
    if isinstance(assignment, dict) and assignment.get("present") is True:
        basis = assignment.get("basis")
        evidence = assignment.get("evidence")
        intents["assignment"] = AssignmentIntent(
            basis=basis if basis in ASSIGNMENT_INTENT_BASES else "implicit",
            confidence=clamp_confidence(assignment.get("confidence")),
            evidence=str(evidence).strip() if isinstance(evidence, str) and evidence.strip() else None,
        ).model_dump()
    append = raw.get("append")
    if isinstance(append, dict) and append.get("present") is True:
        intents["append"] = AppendIntent(confidence=clamp_confidence(append.get("confidence"))).model_dump()
    out_of_context = raw.get("out_of_context")
    if isinstance(out_of_context, dict) and out_of_context.get("present") is True:
        reason = out_of_context.get("reason")
        intents["out_of_context"] = OutOfContextIntent(
            confidence=clamp_confidence(out_of_context.get("confidence")),
            reason=str(reason).strip() if isinstance(reason, str) and reason.strip() else None,
        ).model_dump()
    return intents or None


def parse_structured_transcription_output(raw_text: str) -> dict[str, Any]:
    """Parse and validate strict structured transcription JSON into the capture-intelligence contract.

    Raises ``InvalidOutput`` (retryable → ``invalid_output``) on malformed/missing required content —
    the transcript and patient_information object are required; everything else degrades to a null/empty
    default.
    """
    text = raw_text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidOutput("Audio transcription returned malformed structured JSON") from exc
    if not isinstance(parsed, dict):
        raise InvalidOutput("Audio transcription returned non-object structured JSON")

    transcript = parsed.get("transcript")
    if not isinstance(transcript, str) or not transcript.strip():
        raise InvalidOutput("Audio transcription structured JSON is missing transcript")
    # Normalize spoken numbers (doses, national IDs, phones, dates) to Western/Latin digits so all
    # extracted quantification is comparable regardless of the spoken language. Prose words stay original.
    transcript = normalize_digits_to_latin(transcript.strip())
    language = parsed.get("language")
    if language not in TRANSCRIPTION_LANGUAGES:
        language = "unknown"
    patient_information = parsed.get("patient_information")
    if not isinstance(patient_information, dict):
        raise InvalidOutput("Audio transcription structured JSON is missing patient_information")

    normalized_patient = empty_patient_information(source_text=transcript)
    for field in PATIENT_INFORMATION_FIELDS:
        if field in patient_information:
            normalized_patient[field] = patient_information[field]
    alternates = normalized_patient.get("alternate_transliterations")
    normalized_patient["alternate_transliterations"] = (
        [str(value) for value in alternates if isinstance(value, str)] if isinstance(alternates, list) else []
    )
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
    return StructuredTranscription(
        transcript=transcript,
        language=language,
        patient_information=PatientInformation(**normalized_patient),
        clinical_summary=(
            normalize_digits_to_latin(clinical_summary.strip())
            if isinstance(clinical_summary, str) and clinical_summary.strip()
            else None
        ),
        uncertainties=[str(value) for value in uncertainties if isinstance(value, str)] if isinstance(uncertainties, list) else [],
        intents=normalize_intents(parsed.get("intents")),
    ).model_dump()
