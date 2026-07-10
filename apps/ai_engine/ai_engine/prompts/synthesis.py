"""Single-pass report-synthesis + treatment-extraction prompt (the A↔B contract). Vertical-agnostic."""
from __future__ import annotations

import json
from typing import Any

from ai_engine.contracts.synthesis import SYNTHESIS_SECTIONS
from ai_engine.prompts._shared import domain_framing, vocabulary_line

PROMPT_VERSION = "2026-07-10.synthesis.v13"

# Stable-prefix context layout (G3). MUST stay in lockstep with the backend authority
# `app/services/session_processing.py` (SYNTHESIS_STABLE_KEYS / SYNTHESIS_VOLATILE_KEYS /
# SYNTHESIS_LLM_EXCLUDED_KEYS + `ordered_synthesis_context`). Emitting the blocks in an explicit,
# deterministic order — stable clinic/patient blocks, then captures as one flat append-only list, then
# the per-run volatile blocks LAST — is what lets run N+1's serialized context byte-EXTEND run N's so
# the gateway's exact-prefix cache actually applies. Do NOT re-sort keys here (sort_keys=False).
_STABLE_KEYS: tuple[str, ...] = (
    "schemaVersion",
    "domain",
    "clinic",
    "reportLanguage",
    "aftercareTemplates",
    "assignedPatient",
    "patientSummarizedHistory",
    "patientSafetyFlags",
    "referencePriorVisitTreatments",
    "session",
)
_CAPTURES_KEY = "captures"
_VOLATILE_KEYS: tuple[str, ...] = (
    "changeset",
    "priorDraftTreatments",
    "priorReportModel",
    "priorSafetyReconciliation",
)
_LLM_EXCLUDED_KEYS = frozenset({"rawReportTemplate"})

# Full names for the language directive: a bare code ("en") is a weak signal against the prompt's
# Persian worked examples; the spelled-out name is what actually holds the prose language.
_LANGUAGE_NAMES = {"fa": "Persian (Farsi)", "en": "English"}


def _ordered_context(context: dict[str, Any]) -> dict[str, Any]:
    """Re-key the context into the stable → captures → volatile layout (mirror of the backend)."""
    known = set(_STABLE_KEYS) | {_CAPTURES_KEY} | set(_VOLATILE_KEYS) | _LLM_EXCLUDED_KEYS
    ordered: dict[str, Any] = {}
    for key in _STABLE_KEYS:
        if key in context:
            ordered[key] = context[key]
    if _CAPTURES_KEY in context:
        ordered[_CAPTURES_KEY] = context[_CAPTURES_KEY]
    for key in _VOLATILE_KEYS:
        if key in context:
            ordered[key] = context[key]
    for key in sorted(context):
        if key not in known:
            ordered[key] = context[key]
    return ordered


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
    domain = context.get("domain") if isinstance(context.get("domain"), dict) else {}
    area_codes = [value for value in (domain.get("areaCodes") or []) if isinstance(value, str) and value.strip()]
    area_code_line = (
        "- areaCode: ALSO set a canonical English anatomical slug identifying the treated area — this is "
        "LANGUAGE-INDEPENDENT (always English, regardless of the report language) so the same area keys "
        "identically across visits and languages. "
        + (
            f"Choose the best fit from this closed vocabulary when one applies: {', '.join(area_codes)}. "
            "If none fits, emit your own concise lowercase-hyphenated English slug (e.g. left-cheek). "
            if area_codes
            else "Use a concise lowercase-hyphenated English slug (e.g. cheeks, forehead, left-cheek). "
        )
        + "Leave null only when no anatomical area is stated.\n"
    )
    report_language = context.get("reportLanguage")
    language_name = (
        _LANGUAGE_NAMES.get(report_language.strip().lower(), report_language.strip())
        if isinstance(report_language, str) and report_language.strip()
        else None
    )
    language_directive = (
        f"Write ALL report prose in {language_name} using its native script — EVERY sentence of the "
        "summary, sections, and uncertainties, even when the captures are in another language. The "
        "worked examples in these instructions are Persian for illustration only; they never change "
        "the report language."
        if language_name
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
                "Values render in the report language (the display language); the ONE exception is "
                "areaCode, which is always a canonical English slug (see below) so it is stable across "
                "languages.\n"
                f"- sections: populate these fixed section ids, in this order: {section_lines}. Each "
                "section has id, title, and blocks. A block is either {\"type\":\"paragraph\",\"text\":...} "
                "or {\"type\":\"image\",\"captureId\":<a photo captureId from the context>,\"caption\":...}. "
                "Reference each photo captureId in AT MOST ONE image block across the whole report. "
                "Leave a section's blocks empty ([]) when the captures do not support it — never pad it.\n"
                f"- {language_directive} Write the DESCRIPTIVE treatment fields — area, product (the "
                "generic/category, e.g. فیلر/ژل, بوتاکس), and unit (e.g. واحد, سی‌سی) — in the REPORT "
                "LANGUAGE using its native script; prefer the clinician's own word when they gave one "
                "in that language. "
                "Do NOT emit an English category (\"filler\", \"botox\", \"unit\") in a Persian report, "
                "and do NOT emit a Persian category in an English report — map it to the standard "
                "English term («بوتاکس» → Botox, «ژل/فیلر» → filler, «واحد» → unit, «سی‌سی» → cc). "
                "Keep VERBATIM in their original script: brand names, lot numbers, patient/clinician "
                "quotes, and quantityText (e.g. «۲ سی‌سی») — never translate or romanize these, and never "
                "normalize «۲» to \"2\" in quantityText.\n"
                f"{vocab_line}"
                "- treatments: one TreatmentItem per distinct treatment mentioned, with core fields "
                "area, product, brand, quantity (number or null), unit, quantityText (VERBATIM original "
                "script), lot (dictated or read off a product-label photo), confidence (0..1), status "
                "(see TREATMENT STATUS below), sourceCaptureIds, evidence, carriedForward, "
                "supersedesCaptureId, and an open attributes map (needleGauge, depth, device, sessions, "
                "…). `quantity` is the NUMERIC value regardless of how it was spoken — parse number words "
                "(«سه سی‌سی» → quantity 3, «بیست واحد» → 20) as well as digits; `quantityText` stays "
                "VERBATIM as spoken/written — never rewrite digits as words or words as digits there. "
                "The treatment-performed section is a prose MIRROR of the PERFORMED treatments — keep "
                "them consistent; do not list a planned treatment there.\n"
                f"{area_code_line}"
                "- priorKey: the context's prior-visit treatments (referencePriorVisitTreatments) and "
                "prior-draft treatments each carry a stable `treatmentKey`. If a treatment you emit is THE "
                "SAME treatment as one of those prior rows (a continuation, correction, or carry-forward of "
                "it), set priorKey to that row's treatmentKey. This is only a matching HINT — leave null "
                "for a genuinely new treatment; never invent a key.\n"
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
                "- PROSE after a correction states ONLY the final corrected value. Never restate the "
                "superseded value anywhere in the sections (not even as \"corrected from …\") — the "
                "supersede chain in treatments[] is the audit trail; the report reads as if the final "
                "value was always the value. WORKED EXAMPLE: dictation says «بیست واحد بوتاکس تزریق شد» "
                "then a later capture corrects «دوز درست بیست و چهار واحد شد». WRONG prose: «ابتدا بیست "
                "واحد گفته شد اما با اصلاح بیست و چهار واحد ثبت شد» (narrates the correction). RIGHT "
                "prose: «بیست و چهار واحد بوتاکس روی پیشانی تزریق شد» — the old value appears NOWHERE "
                "in any section.\n"
                "- FINAL CHECK before returning: (1) for every correction you emitted, scan your summary, "
                "sections, and uncertainties for the SUPERSEDED value (when SCANNING, treat digits and "
                "words as the same value — «بیست واحد» = «۲۰ واحد»; this equivalence is for scanning "
                "PROSE only and never rewrites quantityText, which stays verbatim as spoken); if it "
                "appears anywhere, rewrite that sentence with only the final value. (2) confirm every "
                "prose sentence is written in the report language the instructions state — no sentence "
                "may fall back to the captures' language.\n"
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
                "TREATMENT STATUS (performed vs planned) — set `status` on EVERY treatment:\n"
                "- status='performed': the treatment was actually done THIS visit — a past/completed "
                "statement («تزریق کردم», «زدم», «انجام شد», \"I injected\", \"we did\"). This is the DEFAULT.\n"
                "- status='planned': the clinician states an INTENT or FUTURE action, not something done this "
                "visit — future tense or a next-visit plan («خواهیم کرد», «تزریق می‌کنیم» meaning next time, "
                "«دفعه بعد», «قراره», \"we'll do\", \"we plan to\", \"next session\", \"will inject\"). Still "
                "emit the TreatmentItem (so the plan is recorded) but with status='planned'. A planned "
                "treatment is NOT performed: do NOT put it in the treatment-performed prose, and do NOT "
                "select an aftercare protocol for it (aftercare is for procedures actually performed).\n"
                "- status='uncertain': genuinely ambiguous whether it was performed or only planned. Set "
                "status='uncertain' AND add an uncertainties entry with code 'planned_vs_performed'.\n"
                "Tense/intent decides status — NEVER the confidence field. A clear future-tense treatment is "
                "status='planned' with normal confidence, not a low-confidence performed treatment.\n"
                "Extract ONLY performed or planned treatments. Do NOT create a TreatmentItem for a treatment "
                "the patient DECLINED / refused («قبول نکرد», «نخواست», \"the patient declined\") or one only "
                "recalled from a PRIOR visit as history («دفعه قبل زده بودیم» — done before, not this visit) — "
                "those are neither performed nor planned, so they are not treatments for this visit."
            ),
            (
                "AFTERCARE SELECTION — follow these four steps IN ORDER for `aftercareSelections` "
                "[{templateId, status, note}] over the context's `aftercareTemplates` [{id, name, "
                "procedureType, body}]:\n"
                "STEP 1 — SELECT: every protocol whose procedure was PERFORMED this visit gets exactly one "
                "selection entry (botox+filler visit → BOTH the botox and filler protocols, always). A "
                "mention that a procedure was NOT done («بدون لیزر») only omits THAT procedure's protocol — "
                "it never reduces the others. Returning [] when performed procedures have matching "
                "templates is ALWAYS wrong; [] is only for no-performed-procedures or no-templates.\n"
                "STEP 2 — for each selected protocol, default status='applies' (note=null). A dictation "
                "that says nothing about this protocol, or RESTATES its own advice (same value, reworded), "
                "is 'applies'.\n"
                "STEP 3 — upgrade to status='conflicts' ONLY when a dictated instruction meets ALL of: "
                "(a) it concerns THIS procedure — an instruction naming a procedure or its area binds only "
                "to that procedure's protocol; a generic instruction is tested against each protocol via "
                "(b); (b) the protocol's OWN body addresses the SAME literal topic (a sun rule can conflict "
                "only with a protocol whose body mentions sun; a body that mentions only heat/sauna is a "
                "DIFFERENT topic — no conflict); (c) the VALUES differ (3 days vs 1 week). Then note = ONE "
                "report-language sentence quoting both values. If any of (a)(b)(c) fails, stay 'applies'.\n"
                "WORKED EXAMPLE — dictation: «تا یک هفته از آفتاب پرهیز کنه»; botox protocol body: «تا ۳ "
                "روز از آفتاب مستقیم پرهیز»; filler protocol body: «تا ۲ هفته از حرارت زیاد (سونا) "
                "پرهیز». Botox → 'conflicts' (both address SUN; one week ≠ three days — quote both). "
                "Filler → 'applies' (its body never mentions sun; heat/sauna is a different topic). "
                "Always apply this exact pattern: flag the protocol whose body shares the instruction's "
                "topic, keep the other at applies.\n"
                "STEP 4 — status='superseded' when the clinician dictated their OWN full aftercare "
                "REPLACING that protocol; note = one short report-language sentence saying so.\n"
                "The clinician's words always win over a protocol; never silently include a protocol that "
                "contradicts what they said."
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
                "- Safety errs toward INCLUSION: when a statement about this patient's current state "
                "plausibly reads as an allergy / contraindication / consent concern, include it — the "
                "clinician removes a wrong one. Return [] when no capture states any such thing.\n"
                "- NOT a flag — CHECK BEFORE EMITTING each flag: re-read the WHOLE sentence (and any later "
                "capture). If the sentence itself negates, resolves, or attributes the condition to someone "
                "else, do NOT emit it: a RESOLVED or negated concern («قبلاً به پنی‌سیلین حساسیت داشت ولی "
                "تست جدید منفی بود» — the capture itself says it no longer applies); a FAMILY member's "
                "condition («مادرش آلرژی داره» — someone else, not this patient); a HYPOTHETICAL the "
                "capture negates. WORKED EXAMPLE: «اگر باردار بود بوتاکس نمی‌زدیم، ولی باردار نیست» — "
                "WRONG: a pregnancy contraindication flag. RIGHT: no flag at all — the sentence states the "
                "patient is NOT pregnant; a condition mentioned only to be denied is not a current state. "
                "Matching a keyword in the kind list (باردار, حساسیت, …) is NOT enough — the flag must "
                "state THIS patient's CURRENT allergy/contraindication/consent state."
            ),
            (
                "META-SPEECH EXCLUSION (administrative / non-clinical talk): a capture can interleave "
                "clinical dictation with talk directed at STAFF or the APP that is NOT part of the visit "
                "record — e.g. «این رو برای منشی بفرست», «به سیستم بگو نوبت بعدی رو ثبت کنه», «ضبط رو نگه "
                "دار», «فایل قبلی رو پاک کن», \"send this to reception\", \"remind me to call them\", "
                "\"stop the recording\". NEVER let such administrative/meta instructions leak into the "
                "report — not the summary, not any section's prose, not a treatment, aftercare, or safety "
                "flag. Extract ONLY the clinical substance of the visit (assessment, what was performed, "
                "plan, genuine allergy/contraindication/consent). If a capture is ENTIRELY meta/"
                "administrative with no clinical content, contribute nothing from it. A scheduling or "
                "app-command sentence is never a treatment and never a safety flag."
            ),
            (
                "uncertainties: a list of items, each an object {code, text}. `text` is a short "
                "human-readable sentence for anything a clinician should confirm; `code` is the "
                "machine-readable reason, EXACTLY one of: ambiguous_correction (correction vs addition is "
                "unclear), missing_lot (a lot number is expected but absent), low_confidence (a product/"
                "field the model is unsure of), carried_forward_dose (a dose carried from a prior visit), "
                "ambiguous_quantity (the dose/amount itself is unclear), planned_vs_performed (unsure "
                "whether a treatment was performed or only planned), other (anything else). Return ONLY "
                "strict JSON, no markdown, no code fences."
            ),
            f"Session context (stable clinic/patient blocks, then captures, then the per-run update "
            f"blocks — changeset, prior draft, prior report):\n{json.dumps(_ordered_context(context), ensure_ascii=False, sort_keys=False)}",
        )
    )
