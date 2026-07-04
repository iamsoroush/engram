"""Photo caption prompt: an OBJECTIVE image→text description + pairing/OOC attributes (never a diagnosis)."""
from __future__ import annotations

import json
from typing import Any

from ai_engine.prompts._shared import domain_framing, enrichment_language_directive

PROMPT_VERSION = "2026-07-04.caption.v1"


def build(enrichment_context: dict[str, Any] | None) -> str:
    """Build the instruction prompt for photo description + attribute extraction.

    The caption is a NEUTRAL textual stand-in for the image (so downstream text-only AI jobs can read
    the photo) — an objective description of what is visibly present, NOT a clinical assessment.
    Vertical-agnostic via the domain descriptor; a product-label shot reads the lot/brand text.
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
