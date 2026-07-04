"""Single-pass report-synthesis + treatment-extraction prompt (the A↔B contract). Vertical-agnostic."""
from __future__ import annotations

import json
from typing import Any

from ai_engine.contracts.synthesis import SYNTHESIS_SECTIONS
from ai_engine.prompts._shared import domain_framing, vocabulary_line

PROMPT_VERSION = "2026-07-04.synthesis.v1"


def build(processing_context: dict[str, Any]) -> str:
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
    vocab_line = vocabulary_line(label, vocabulary)
    section_lines = "; ".join(f"{section_id} ({title})" for section_id, title in SYNTHESIS_SECTIONS)
    return "\n\n".join(
        (
            f"You are Engram, synthesizing ONE per-visit clinical report and extracting the performed "
            f"treatments for a {label}. Work only from the provided captures (audio transcripts, photo "
            f"captions, and raw text notes) and the prior visit context. Invent nothing.",
            (
                "Produce a strict JSON object with EXACTLY these keys: summary, language, sections, "
                "treatments, uncertainties, aftercareSelections, safetyFlags.\n"
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
                "- product vs brand: `product` is the GENERIC category ONLY (e.g. ژل/فیلر, بوتاکس) — never "
                "put a commercial brand in it. `brand` is the commercial name verbatim (e.g. ژوویدرم/"
                "Juvederm, رستیلین/Restylane, ولوما/Voluma), null if none was said. When the clinician "
                "names a brand (e.g. «ژل ژوویدرم»), set product=«ژل» and brand=«ژوویدرم» — split them, "
                "never merge the brand into product.\n"
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
                "AFTERCARE SELECTION (intelligent, not keyword): the clinic's reusable aftercare protocols "
                "are in the context as `aftercareTemplates` [{id, name, procedureType, body}]. Decide by "
                "CLINICAL RELEVANCE — judge the procedure, not a word match — and return one entry per "
                "applicable protocol in `aftercareSelections` [{templateId, status, note}].\n"
                "- COMPLETENESS: emit a selection for EVERY protocol whose procedure was actually performed "
                "this visit (one per treatment area/product, e.g. a botox+filler visit → BOTH the botox and "
                "filler protocols). Do not omit an applicable protocol just because another one conflicts. "
                "Omit only protocols whose procedure was NOT performed; return [] if none were performed or "
                "there are no templates.\n"
                "- PER-PROCEDURE: compare a protocol ONLY against what the clinician dictated about that "
                "SAME procedure/area — never judge the botox protocol against a filler instruction.\n"
                "- status='applies': that procedure's protocol fits and the clinician dictated nothing that "
                "contradicts it. note=null.\n"
                "- status='conflicts': the clinician DICTATED aftercare for that procedure that DIFFERS from "
                "its protocol (e.g. botox protocol says avoid sun 3 days, clinician said 1 week). The "
                "clinician's words win — set note to ONE sentence in the report language naming the specific "
                "difference and quoting both values.\n"
                "- status='superseded': the clinician dictated their OWN full aftercare that REPLACES that "
                "protocol entirely. note = one short sentence in the report language saying so.\n"
                "Prefer the clinician's dictated aftercare over a fixed protocol whenever they differ; never "
                "silently include a protocol that contradicts what the clinician said."
            ),
            (
                "SAFETY FLAGS (highest priority — surface, never gate): scan EVERY capture for any ALLERGY, "
                "CONTRAINDICATION, or CONSENT statement actually made this visit, and return one entry per "
                "distinct mention in `safetyFlags` [{kind, text, sourceCaptureIds}].\n"
                "- kind='allergy': a stated allergy or prior adverse reaction (e.g. «به لیدوکائین حساسیت "
                "داره», «آلرژی به پنی‌سیلین»).\n"
                "- kind='contraindication': a stated reason to avoid or use caution with a treatment — "
                "pregnancy/breastfeeding, anticoagulants, active infection at the site, recent isotretinoin, "
                "autoimmune or keloid history, a drug interaction the clinician flags.\n"
                "- kind='consent': a statement about informed consent for a procedure — given, declined, "
                "withdrawn, or still pending/required (e.g. «رضایت‌نامه امضا شد», «هنوز رضایت نگرفتیم»).\n"
                "- text: ONE short clinical sentence, in the REPORT LANGUAGE using its native script, stating "
                "exactly what the capture says (quote the clinician's own words where possible). NEVER "
                "translate, soften, or generalize the clinical content.\n"
                "- GROUNDING: flag ONLY what a capture EXPLICITLY states. Invent nothing; never infer an "
                "allergy or contraindication from the treatment itself, and NEVER emit a negative/absence "
                "statement (no «no known allergies», no «مشکلی نداشت»). Set sourceCaptureIds to the "
                "captureId(s) that state it.\n"
                "- Safety errs toward INCLUSION: when a statement plausibly reads as an allergy / "
                "contraindication / consent concern, include it — the clinician removes a wrong one. Return "
                "[] only when no capture states any such thing."
            ),
            (
                "uncertainties: a list of short human-readable sentences for anything a clinician should "
                "confirm (ambiguous correction, a missing-but-expected lot number, a low-confidence "
                "product, a carried-forward dose). Return ONLY strict JSON, no markdown, no code fences."
            ),
            f"Session context (captures, prior report draft, changeset, prior-visit treatments):\n{json.dumps(context, ensure_ascii=False, sort_keys=True)}",
        )
    )
