"""Shared input corpus for the typed-contract parity tests (Axis-1 increment 3).

The corpus deliberately over-weights MALFORMED / partial / edge inputs — the whole risk of swapping
tolerant dict-shaping for typed models is that validation silently tightens, so every drop-a-field,
wrong-type, and out-of-range case a parser tolerates today must appear here. ``tests/contract_goldens.json``
holds the OLD parsers' output for each case (captured from the code at the increment's branch point via
``scripts capture``); ``test_contract_parity`` asserts the NEW model-backed parsers reproduce it exactly.

Each case is ``(label, args)`` where ``args`` is the positional/keyword input for the parser under test.
"""
from __future__ import annotations

import json

# --- transcription (parse_structured_transcription_output) --------------------------------------

TRANSCRIPTION_CASES: list[tuple[str, str]] = [
    ("empty", ""),
    ("whitespace", "   \n  "),
    ("not_json", "transcript: not json"),
    ("json_array", "[1, 2, 3]"),
    ("json_string", '"just a string"'),
    ("missing_transcript", '{"language": "fa", "patient_information": {}}'),
    ("blank_transcript", '{"transcript": "   ", "patient_information": {}}'),
    ("missing_patient_information", '{"transcript": "hello"}'),
    ("patient_information_not_dict", '{"transcript": "hi", "patient_information": "nope"}'),
    ("minimal_valid", '{"transcript": "ok", "language": "en", "patient_information": {}}'),
    ("unknown_language", '{"transcript": "ok", "language": "martian", "patient_information": {}}'),
    ("no_language", '{"transcript": "ok", "patient_information": {}}'),
    (
        "persian_digits",
        json.dumps(
            {
                "transcript": "بیمار ۲ سی‌سی ژل دریافت کرد",
                "language": "fa",
                "patient_information": {"national_id": "۱۲۳۴۵۶۷۸۹۰", "phone": "۰۹۱۲۳۴۵۶۷۸۹", "confidence": 0.5},
            },
            ensure_ascii=False,
        ),
    ),
    (
        "full_patient",
        json.dumps(
            {
                "transcript": "سلام Sara Nazari for cheek filler follow-up.",
                "language": "mixed",
                "patient_information": {
                    "raw_mentioned_name": "  سارا نظری ",
                    "standardized_display_name": "Sara Nazari",
                    "alternate_transliterations": ["Sara Nazari", 5, "Saraa Nazari", None],
                    "national_id": "0012345678",
                    "phone": "09121234567",
                    "date_of_birth": None,
                    "evidence": "Name and national ID spoken.",
                    "confidence": 0.82,
                },
                "clinical_summary": "  Cheek filler follow-up.  ",
                "uncertainties": ["dob missing", 7, None, "also this"],
            },
            ensure_ascii=False,
        ),
    ),
    (
        "confidence_out_of_range",
        '{"transcript": "x", "language": "en", "patient_information": {"confidence": 5}}',
    ),
    (
        "confidence_non_numeric",
        '{"transcript": "x", "language": "en", "patient_information": {"confidence": "high"}}',
    ),
    (
        "alternates_not_list",
        '{"transcript": "x", "language": "en", "patient_information": {"alternate_transliterations": "one"}}',
    ),
    (
        "blank_string_fields_become_null",
        '{"transcript": "x", "language": "en", "patient_information": {"raw_mentioned_name": "   ", "national_id": ""}}',
    ),
    (
        "explicit_assignment_intent",
        json.dumps(
            {
                "transcript": "نام بیمار عوض شه به سروش معاصد.",
                "language": "fa",
                "patient_information": {"raw_mentioned_name": "سروش معاصد", "confidence": 0.7},
                "intents": {
                    "assignment": {"present": True, "basis": "explicit", "confidence": 0.9, "evidence": "change the patient to Soroush"},
                    "append": {"present": False, "confidence": 0.0},
                    "out_of_context": {"present": False, "confidence": 0.0, "reason": None},
                },
            },
            ensure_ascii=False,
        ),
    ),
    (
        "implicit_assignment_intent",
        '{"transcript": "خانم قاسمی بوتاکس پیشانی.", "language": "fa", '
        '"patient_information": {"raw_mentioned_name": "خانم قاسمی"}, '
        '"intents": {"assignment": {"present": true, "basis": "implicit", "confidence": 0.6}}}',
    ),
    ("intents_non_dict", '{"transcript": "ok2", "language": "en", "patient_information": {}, "intents": "nonsense"}'),
    ("intents_empty", '{"transcript": "ok", "language": "en", "patient_information": {}, "intents": {}}'),
    (
        "intents_unknown_basis_oob_confidence",
        '{"transcript": "ok", "language": "en", "patient_information": {}, '
        '"intents": {"assignment": {"present": true, "basis": "weird", "confidence": 5}}}',
    ),
    (
        "intents_append_and_ooc",
        '{"transcript": "ok", "language": "en", "patient_information": {}, '
        '"intents": {"append": {"present": true, "confidence": 0.4}, '
        '"out_of_context": {"present": true, "confidence": 2, "reason": " not clinical "}}}',
    ),
    (
        "intents_all_present_false",
        '{"transcript": "ok", "language": "en", "patient_information": {}, '
        '"intents": {"assignment": {"present": false}, "append": {"present": false}, "out_of_context": {"present": false}}}',
    ),
    (
        "fenced_json",
        '```json\n{"transcript": "fenced ok", "language": "en", "patient_information": {}}\n```',
    ),
    (
        "uncertainties_not_list",
        '{"transcript": "x", "language": "en", "patient_information": {}, "uncertainties": "nope"}',
    ),
]

# --- normalize_intents (called directly) --------------------------------------------------------

INTENTS_CASES: list[tuple[str, object]] = [
    ("none", None),
    ("string", "x"),
    ("empty_dict", {}),
    ("all_false", {"assignment": {"present": False}, "append": {"present": False}}),
    (
        "append_and_ooc",
        {
            "append": {"present": True, "confidence": 0.4},
            "out_of_context": {"present": True, "confidence": 2, "reason": " not clinical "},
        },
    ),
    ("assignment_missing_basis", {"assignment": {"present": True, "confidence": 0.5}}),
    ("assignment_explicit", {"assignment": {"present": True, "basis": "explicit", "confidence": 0.9, "evidence": " e "}}),
    ("assignment_bad_basis", {"assignment": {"present": True, "basis": "??", "confidence": -3}}),
    ("assignment_not_dict", {"assignment": "x", "append": 5}),
    ("ooc_blank_reason", {"out_of_context": {"present": True, "reason": "   "}}),
    ("append_no_confidence", {"append": {"present": True}}),
]

# --- caption (parse_caption_output) -------------------------------------------------------------

CAPTION_CASES: list[tuple[str, str]] = [
    ("empty", "  "),
    ("blank_caption_json", '{"caption": ""}'),
    ("not_json_plain", "Just a plain caption with no JSON."),
    ("not_json_persian_digits", "لات ۰۴۰۲۹، ۲ سی‌سی"),
    (
        "structured_full",
        json.dumps(
            {
                "caption": " Left cheek asymmetry. ",
                "display": "Left cheek asymmetry.",
                "confidence": 0.8,
                "outOfContext": None,
                "pairing": {"region": " cheek ", "laterality": "Left", "view": "front", "phase": "Before", "isProductLabel": False},
                "uncertainties": [" confirm area ", 5, None],
            },
            ensure_ascii=False,
        ),
    ),
    (
        "ooc_present",
        json.dumps({"caption": "A parking receipt.", "outOfContext": {"present": True, "reason": " not clinical ", "confidence": 0.9}}),
    ),
    (
        "ooc_present_no_reason",
        json.dumps({"caption": "x", "outOfContext": {"present": True, "confidence": 3}}),
    ),
    (
        "confidence_bool_ignored",
        json.dumps({"caption": "x", "confidence": True}),
    ),
    (
        "confidence_missing",
        json.dumps({"caption": "x"}),
    ),
    (
        "pairing_unknown_enums",
        json.dumps({"caption": "x", "pairing": {"region": "Forehead", "laterality": "sideways", "phase": "weird", "isProductLabel": True}}),
    ),
    (
        "display_same_text",
        json.dumps({"caption": "Decosalin spray, batch 04029", "display": "**Decosalin** spray, batch **۰۴۰۲۹**"}),
    ),
    (
        "display_diverged",
        json.dumps({"caption": "Decosalin spray, batch 04029", "display": "**A totally different sentence.**"}),
    ),
    (
        "persian_digits_in_caption",
        json.dumps({"caption": "جعبه ژل، شماره بچ ۰۴۰۲۹"}, ensure_ascii=False),
    ),
    (
        "fenced",
        '```json\n{"caption": "fenced caption"}\n```',
    ),
    (
        "uncertainties_not_list",
        json.dumps({"caption": "x", "uncertainties": "nope"}),
    ),
    (
        "pairing_not_dict",
        json.dumps({"caption": "x", "pairing": "nope"}),
    ),
]

# --- patient memory (parse_patient_memory_output) -----------------------------------------------

MEMORY_CASES: list[tuple[str, str]] = [
    ("empty", ""),
    ("not_json", "not json at all"),
    ("summary_only", '{"summary":"S"}'),
    ("empty_sections", '{"summary":"S","history":{"snapshot":"x","sections":[]}}'),
    ("missing_snapshot", '{"summary":"S","history":{"sections":[{"label":"L","body":"B"}]}}'),
    ("blank_summary", '{"summary":"   ","history":{"snapshot":"x","sections":[{"label":"L","body":"B"}]}}'),
    (
        "valid",
        '{"summary":" S ","history":{"snapshot":"snap","sections":[{"label":"L","body":"B"}],"visits":[]}}',
    ),
    (
        "valid_with_card",
        json.dumps(
            {
                "summary": "S",
                "history": {"snapshot": "snap", "sections": [{"label": "Story so far", "body": "b"}], "visits": []},
                "card": {"storySoFar": "one", "rightNow": "two", "flags": [{"kind": "allergy", "label": "x"}]},
            }
        ),
    ),
    (
        "card_not_dict",
        '{"summary":"S","history":{"snapshot":"snap","sections":[{"label":"L","body":"B"}]},"card":"nope"}',
    ),
    (
        "fenced_json",
        '```json\n{"summary":"S","history":{"snapshot":"snap","sections":[{"label":"L","body":"B"}]}}\n```',
    ),
    (
        "leading_prose",
        'Here is the memory: {"summary":"S","history":{"snapshot":"snap","sections":[{"label":"L","body":"B"}]}} done',
    ),
    ("history_not_dict", '{"summary":"S","history":"nope"}'),
    ("sections_not_list", '{"summary":"S","history":{"snapshot":"x","sections":"nope"}}'),
]

# --- qa draft (parse_qa_draft_output) -----------------------------------------------------------

QA_DRAFT_CASES: list[tuple[str, str]] = [
    ("empty", "   "),
    ("plain", "Hi Sara, rest up.  "),
    ("fenced_no_lang", "```\nHi Sara, rest up.\n```"),
    ("fenced_incomplete", "```only-one-fence"),
    ("multiline", "Line one.\nLine two."),
]

# --- qa revise (parse_qa_revise_output) ---------------------------------------------------------

QA_REVISE_CASES: list[tuple[str, str]] = [
    ("empty", ""),
    ("whitespace", "   "),
    ("not_json", "not json"),
    ("json_array", '["not","an","object"]'),
    ("valid_replace", '{"mode":"replace","reply":"Hello there."}'),
    ("fenced", '```json\n{"mode":"revise","reply":"Trimmed."}\n```'),
    ("unknown_mode", '{"mode":"weird","reply":"R"}'),
    ("missing_mode", '{"reply":"R"}'),
    ("missing_reply", '{"mode":"revise"}'),
    ("blank_reply", '{"mode":"revise","reply":"  "}'),
    ("reply_padded", '{"mode":"replace","reply":"  padded  "}'),
]

# --- safety reconcile (parse_safety_reconcile_output) -------------------------------------------

SAFETY_RECONCILE_KEYS = ["allergy|penicillin", "allergy|penicillin sensitivity", "consent|signed"]

SAFETY_RECONCILE_CASES: list[tuple[str, str]] = [
    ("empty", ""),
    ("whitespace", "   "),
    ("not_json", "not json"),
    ("no_decisions", '{"nope":1}'),
    ("decisions_not_list", '{"decisions":"nope"}'),
    (
        "keep_dup_superseded",
        '{"decisions":['
        '{"key":"allergy|penicillin","status":"keep"},'
        '{"key":"allergy|penicillin sensitivity","status":"duplicate","ofKey":"allergy|penicillin"},'
        '{"key":"consent|signed","status":"superseded","ofKey":"allergy|penicillin"}]}',
    ),
    ("unknown_key", '{"decisions":[{"key":"not|a|candidate","status":"keep"}]}'),
    ("unknown_status", '{"decisions":[{"key":"allergy|penicillin","status":"bogus"}]}'),
    ("ofkey_not_candidate", '{"decisions":[{"key":"allergy|penicillin","status":"duplicate","ofKey":"ghost|key"}]}'),
    ("ofkey_equals_key", '{"decisions":[{"key":"allergy|penicillin","status":"duplicate","ofKey":"allergy|penicillin"}]}'),
    ("item_not_dict", '{"decisions":[5, "x", {"key":"consent|signed","status":"keep"}]}'),
    ("fenced", '```json\n{"decisions":[{"key":"consent|signed","status":"keep"}]}\n```'),
]

# --- session synthesis (parse_session_synthesis_output) -----------------------------------------
# Each case is (label, raw_text, source_capture_ids, report_language).

SYNTHESIS_CASES: list[tuple[str, str, list[str], object]] = [
    ("empty", "", [], None),
    ("not_json", "not json", [], None),
    ("no_summary", '{"language":"fa"}', [], None),
    ("blank_summary", '{"summary":"  ","language":"fa"}', [], None),
    ("json_array", "[1,2]", [], None),
    (
        "minimal",
        '{"summary":"A visit summary."}',
        ["cap-a"],
        None,
    ),
    (
        "full_fa",
        json.dumps(
            {
                "summary": " Follow-up gel touch-up. ",
                "language": "fa",
                "sections": [
                    {"id": "visit-summary", "title": "X", "blocks": [{"type": "paragraph", "text": " بیمار آمد. "}]},
                    {"id": "treatment-performed", "title": "Y", "blocks": [{"type": "paragraph", "text": "ژل ۳ سی‌سی"}, {"type": "bogus", "text": "drop me"}]},
                    {"id": "media", "title": "Z", "blocks": [{"type": "image", "captureId": " cap-a ", "caption": " photo "}, {"type": "image"}]},
                    {"id": "unknown-section", "title": "W", "blocks": []},
                ],
                "treatments": [
                    {
                        "area": " left cheek ",
                        "product": "gel",
                        "brand": "Juvederm",
                        "quantity": 3,
                        "unit": "cc",
                        "quantityText": "۳ سی‌سی",
                        "lot": None,
                        "confidence": 0.9,
                        "sourceCaptureIds": ["cap-a", 5, None],
                        "evidence": "spoken",
                        "carriedForward": False,
                        "supersedesCaptureId": None,
                        "attributes": {"needleGauge": "27G"},
                    },
                    {"area": "  ", "product": "  "},
                    {"not": "a treatment"},
                    "bogus",
                    {"area": "forehead", "product": None, "confidence": "high", "quantity": True, "attributes": "nope", "sourceCaptureIds": "nope"},
                ],
                "uncertainties": ["ambiguous dose", 9, None],
                "aftercareSelections": [
                    {"templateId": "t1", "status": "applies", "note": None},
                    {"templateId": "t2", "status": "conflicts", "note": " differs "},
                    {"templateId": "  ", "status": "applies"},
                    {"templateId": "t3", "status": "bogus"},
                    "nope",
                ],
                "safetyFlags": [
                    {"kind": "allergy", "text": " لیدوکائین ", "sourceCaptureIds": ["cap-a", 3]},
                    {"kind": "bogus", "text": "x"},
                    {"kind": "consent", "text": "   "},
                    {"kind": "contraindication", "text": "pregnant"},
                    "nope",
                ],
            },
            ensure_ascii=False,
        ),
        ["cap-a", "cap-b"],
        "fa",
    ),
    (
        "full_en_report_language",
        json.dumps(
            {
                "summary": "Summary.",
                "language": "en",
                "sections": [{"id": "assessment", "title": "orig", "blocks": [{"type": "paragraph", "text": "note"}]}],
                "treatments": [],
                "uncertainties": [],
                "aftercareSelections": [],
                "safetyFlags": [],
            }
        ),
        [],
        "en",
    ),
    (
        "unknown_language_defaults_mixed",
        '{"summary":"S","language":"martian","sections":[],"treatments":[]}',
        [],
        None,
    ),
    (
        "fenced",
        '```json\n{"summary":"Fenced summary."}\n```',
        ["cap-x"],
        "fa",
    ),
    (
        "sections_not_list",
        '{"summary":"S","sections":"nope","treatments":"nope","aftercareSelections":"nope","safetyFlags":"nope","uncertainties":"nope"}',
        ["cap-a"],
        None,
    ),
]
