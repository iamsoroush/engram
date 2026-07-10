#!/usr/bin/env python3
"""Golden-set eval for REPORT SYNTHESIS — SECTIONS (Job 3, the narrative half of the A↔B contract).

``treatments_eval`` + ``aftercare_conflict_eval`` cover the structured half of synthesis; this covers
the prose: the fixed report sections the model fills. It runs the REAL single-pass synthesis
(``synthesize_session_report``) over synthetic Farsi visit transcripts — no recordings needed — and
scores two tiers (shared harness in ``_common.py``):

* **Safety gates** — deterministic: image blocks reference ONLY real photo captureIds (no hallucinated
  media refs), empty sections stay empty (a consult-only visit → no treatment-performed prose),
  expected sections carry content, native-script prose (no romanization), all fixed section ids present.
* **Quality (LLM judge)** — grounding (no invented clinical facts beyond the captures), native script,
  completeness (the visit's substance is reflected), no-hallucination. Advisory by default.

Run::

    docker exec notari-main-ai-engine-1 python /app/eval/report_sections_eval.py

No gateway → the synthetic cases SKIP; deterministic gate self-tests still run. Exit = SAFETY only
unless EVAL_STRICT_QUALITY=1.
"""
from __future__ import annotations

import pathlib
import sys
from typing import Any

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/eval")
sys.path.insert(0, ".")
try:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
except NameError:
    pass

from _common import (  # noqa: E402
    DEFAULT_MIN_SCORE,
    EVAL_VOTES,
    STRICT_QUALITY,
    capture_prompt_version,
    contains,
    env_models,
    exit_code,
    gate_votes,
    gateway_configured,
    judge,
    latin_offenders,
    min_score,
    quality_line,
    write_scorecard,
)
from ai_engine.processing import SYNTHESIS_SECTION_IDS, synthesize_session_report  # noqa: E402

DOMAIN = {"label": "aesthetics clinic", "vocabulary": ["بوتاکس", "فیلر", "ژل", "واحد", "سی‌سی"]}
JUDGE_DIMENSIONS = ("grounding", "nativeScript", "completeness", "noHallucination")
# Common English clinical loanwords the synthesis model uses in otherwise-Persian prose (accepted
# "Finglish"). The no-Latin gate still catches genuine romanization (e.g. «filler tzrigh shod be gone»
# → tzrigh/shod/be/gone remain offenders). Keep this list minimal and clinical.
PROSE_ALLOWED_LATIN = ["aftercare", "filler", "botox", "gel", "cc", "ml", "unit", "lot", "lip", "cheek", "forehead"]


def _audio(capture_id: str, transcript: str) -> dict[str, Any]:
    return {"captureId": capture_id, "type": "audio", "transcript": transcript}


def _photo(capture_id: str, caption: str) -> dict[str, Any]:
    return {"captureId": capture_id, "type": "photo", "caption": caption}


def _payload(captures: list[dict[str, Any]], language: str = "fa") -> dict[str, Any]:
    return {
        "job": {"id": "eval-job", "jobType": "session_organize"},
        "session": {"reportTemplateKey": "default"},
        "reportTemplate": {"key": "default"},
        "aiModels": {},
        "sessionProcessingContext": {
            "domain": DOMAIN,
            "reportLanguage": language,
            "captures": {
                "audio": [c for c in captures if c["type"] == "audio"],
                "photos": [c for c in captures if c["type"] == "photo"],
                "text": [c for c in captures if c["type"] == "note"],
            },
            "referencePriorVisitTreatments": [],
        },
    }


def _blocks_by_id(output: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {s.get("id"): (s.get("blocks") or []) for s in (output.get("sections") or []) if isinstance(s, dict)}


def _prose(output: dict[str, Any]) -> str:
    parts: list[str] = []
    for section in output.get("sections") or []:
        for block in section.get("blocks") or []:
            if block.get("type") == "paragraph" and isinstance(block.get("text"), str):
                parts.append(block["text"])
    return "\n".join(parts)


def _image_capture_ids(output: dict[str, Any]) -> list[str]:
    return [
        block.get("captureId")
        for section in (output.get("sections") or [])
        for block in (section.get("blocks") or [])
        if block.get("type") == "image"
    ]


def _report_text(output: dict[str, Any]) -> str:
    """ALL human-facing report text — summary + every section's prose + uncertainties. A safety-critical
    finding (allergy, contraindication, adverse event) must surface SOMEWHERE here, not only in one
    section, so the propagation gate searches the union rather than a single section's prose."""
    parts = [str(output.get("summary") or ""), _prose(output)]
    parts.extend(str(u) for u in (output.get("uncertainties") or []))
    return "\n".join(parts)


# --- Safety gates (deterministic) -----------------------------------------------------------------


def run_gates(output: dict[str, Any], expect: dict[str, Any], photo_ids: set[str]) -> list[str]:
    """Apply the deterministic safety gates to a synthesis output; return failure reasons (empty == pass)."""
    problems: list[str] = []
    by_id = _blocks_by_id(output)

    missing = [section_id for section_id in SYNTHESIS_SECTION_IDS if section_id not in by_id]
    if missing:
        problems.append(f"missing fixed section ids {missing}")

    for capture_id in _image_capture_ids(output):
        if capture_id not in photo_ids:
            problems.append(f"image block refs unknown captureId {capture_id!r} (real photos: {sorted(photo_ids) or '∅'})")

    if expect.get("imageRefsUnique"):
        seen: set[str] = set()
        for capture_id in _image_capture_ids(output):
            if capture_id not in photo_ids:
                continue  # ghost refs are already caught by the unknown-captureId gate above
            if capture_id in seen:
                problems.append(f"image captureId {capture_id!r} referenced more than once")
            seen.add(capture_id)

    for section_id in expect.get("sectionsNonEmpty", []):
        if not by_id.get(section_id):
            problems.append(f"section {section_id!r} empty but expected content")

    for section_id in expect.get("sectionsEmpty", []):
        if by_id.get(section_id):
            problems.append(f"section {section_id!r} has blocks but expected empty")

    prose = _prose(output)
    for token in expect.get("containsFa", []):
        if not contains(prose, token):
            problems.append(f"prose missing required {token!r}")
    any_group = expect.get("containsAnyFa", [])
    if any_group and not any(contains(prose, token) for token in any_group):
        problems.append(f"prose missing all of {any_group!r} (any one required)")
    for banned in expect.get("forbidden", []):
        if contains(prose, banned):
            problems.append(f"forbidden {banned!r} present in prose")
    if expect.get("noLatinWords"):
        offenders = latin_offenders(prose, allow=[*PROSE_ALLOWED_LATIN, *expect.get("allowLatin", [])])
        if offenders:
            problems.append(f"romanized/Latin words in prose: {offenders}")

    # Safety-critical PROPAGATION: a finding stated this visit must survive into the report somewhere
    # (any section, the summary, or uncertainties) — and a negation of it must not appear.
    report_text = _report_text(output)
    for token in expect.get("surfaces", []):
        if not contains(report_text, token):
            problems.append(f"safety-critical {token!r} DROPPED from the whole report")
    for group in expect.get("surfacesAny", []):
        options = group if isinstance(group, list) else [group]
        if not any(contains(report_text, option) for option in options):
            problems.append(f"none of {options} surfaced anywhere in the report")
    for banned in expect.get("forbiddenAnywhere", []):
        if contains(report_text, banned):
            problems.append(f"{banned!r} present anywhere in the report (negation flip / fabrication)")

    return problems


# --- Quality tier: LLM-as-judge -------------------------------------------------------------------

JUDGE_ROLE = (
    "You are a strict clinical-report judge. Compare the CANDIDATE report sections (prose synthesized "
    "from a visit) against the REFERENCE (the raw visit captures: transcripts + photo captions)."
)
JUDGE_RUBRIC = {
    "grounding": "1.0 = every clinical statement in the prose is supported by the reference captures; "
    "0.0 = it asserts products, doses, areas, diagnoses, or instructions NOT present in the captures.",
    "nativeScript": "1.0 = the prose is written in the report language's native script (Persian in "
    "Persian script); lower for romanized Persian or stray translation.",
    "completeness": "1.0 = the visit's substance (what was done / discussed) is reflected in the "
    "relevant sections; lower for meaningful omissions.",
    "noHallucination": "1.0 = nothing invented; lower for any fabricated identity, measurement, date, "
    "or clinical claim.",
}


def judge_sections(reference: str, candidate: str, dimensions: list[str]) -> dict[str, Any]:
    return judge(
        role=JUDGE_ROLE, rubric=JUDGE_RUBRIC, dimensions=dimensions, reference=reference, candidate=candidate,
        reference_label="REFERENCE (raw visit captures)", candidate_label="CANDIDATE (report prose)",
    )


# --- Synthetic cases ------------------------------------------------------------------------------

# Deterministic gate self-tests over synthetic synthesis OUTPUT dicts — prove the matchers catch a
# hallucinated image ref / a non-empty section that should be empty / romanized prose. No gateway.
def _output(sections: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {s["id"]: s for s in sections}
    return {"sections": [by_id.get(sid, {"id": sid, "title": sid, "blocks": []}) for sid in SYNTHESIS_SECTION_IDS]}


GATE_SELF_TESTS: list[dict[str, Any]] = [
    {
        "name": "grounded fa prose + valid image ref passes",
        "output": _output([
            {"id": "visit-summary", "title": "خلاصه", "blocks": [{"type": "paragraph", "text": "ویزیت پیگیری برای تزریق فیلر گونه"}]},
            {"id": "media", "title": "تصاویر", "blocks": [{"type": "image", "captureId": "p1", "caption": "گونه چپ"}]},
        ]),
        "photo_ids": {"p1"},
        "expect": {"sectionsNonEmpty": ["visit-summary"], "noLatinWords": True},
        "expectGatesPass": True,
    },
    {
        "name": "hallucinated image captureId FAILS the media-ref gate",
        "output": _output([{"id": "media", "title": "تصاویر", "blocks": [{"type": "image", "captureId": "ghost", "caption": "x"}]}]),
        "photo_ids": {"p1"},
        "expect": {},
        "expectGatesPass": False,
        "expectReasonContains": "unknown captureId",
    },
    {
        "name": "same real photo referenced by two image blocks FAILS imageRefsUnique",
        "output": _output([{"id": "media", "title": "تصاویر", "blocks": [
            {"type": "image", "captureId": "p1", "caption": "گونه چپ"},
            {"type": "image", "captureId": "p1", "caption": "گونه چپ دوباره"},
        ]}]),
        "photo_ids": {"p1", "p2"},
        "expect": {"imageRefsUnique": True},
        "expectGatesPass": False,
        "expectReasonContains": "referenced more than once",
    },
    {
        "name": "each real photo referenced at most once PASSES imageRefsUnique",
        "output": _output([{"id": "media", "title": "تصاویر", "blocks": [
            {"type": "image", "captureId": "p1", "caption": "گونه چپ"},
            {"type": "image", "captureId": "p2", "caption": "گونه راست"},
        ]}]),
        "photo_ids": {"p1", "p2"},
        "expect": {"imageRefsUnique": True},
        "expectGatesPass": True,
    },
    {
        "name": "non-empty treatment section FAILS when expected empty (consult-only)",
        "output": _output([{"id": "treatment-performed", "title": "درمان", "blocks": [{"type": "paragraph", "text": "بوتاکس"}]}]),
        "photo_ids": set(),
        "expect": {"sectionsEmpty": ["treatment-performed"]},
        "expectGatesPass": False,
        "expectReasonContains": "expected empty",
    },
    {
        "name": "romanized prose FAILS the no-Latin gate",
        "output": _output([{"id": "visit-summary", "title": "خلاصه", "blocks": [{"type": "paragraph", "text": "filler tzrigh shod be gone"}]}]),
        "photo_ids": set(),
        "expect": {"noLatinWords": True},
        "expectGatesPass": False,
        "expectReasonContains": "romanized",
    },
    {
        "name": "empty section FAILS when content expected",
        "output": _output([{"id": "visit-summary", "title": "خلاصه", "blocks": []}]),
        "photo_ids": set(),
        "expect": {"sectionsNonEmpty": ["visit-summary"]},
        "expectGatesPass": False,
        "expectReasonContains": "expected content",
    },
    {
        "name": "dropped allergy FAILS the surfaces propagation gate",
        "output": _output([{"id": "visit-summary", "title": "خلاصه", "blocks": [{"type": "paragraph", "text": "تزریق فیلر گونه انجام شد"}]}]),
        "photo_ids": set(),
        "expect": {"surfacesAny": [["لیدوکائین", "حساسیت"]]},
        "expectGatesPass": False,
        "expectReasonContains": "surfaced anywhere",
    },
    {
        "name": "negation flip FAILS the forbiddenAnywhere gate",
        "output": _output([{"id": "assessment", "title": "ارزیابی", "blocks": [{"type": "paragraph", "text": "بیمار حساسیتی ندارد"}]}]),
        "photo_ids": set(),
        "expect": {"forbiddenAnywhere": ["حساسیتی ندارد"]},
        "expectGatesPass": False,
        "expectReasonContains": "negation flip",
    },
]

# Real synthetic-transcript cases — these RUN the gateway synthesis (a real eval today, no recordings).
CASES: list[dict[str, Any]] = [
    {
        "name": "botox+filler visit → treatment-performed has prose, native script",
        "captures": [_audio("c1", "بیست واحد بوتاکس روی پیشانی و یک سی‌سی ژل توی گونه چپ تزریق شد")],
        "expect": {"sectionsNonEmpty": ["visit-summary", "treatment-performed"], "noLatinWords": True},
        "judge": True,
    },
    {
        # NOTE: `treatment-performed` is backend-OWNED (re-rendered from treatments[]), so we don't gate
        # on the MODEL's blocks there — treatments_eval covers "consult-only → treatments=[]". Here we
        # check the model summarizes the consult, stays native-script, and the judge checks grounding.
        "name": "consult only → grounded native-script summary (no invented treatment)",
        "captures": [_audio("c1", "امروز فقط مشاوره بود و هیچ تزریقی انجام نشد. درباره گزینه‌های فیلر گونه صحبت کردیم")],
        "expect": {"sectionsNonEmpty": ["visit-summary"], "noLatinWords": True},
        "judge": True,
    },
    {
        "name": "visit with a photo → image blocks reference only real captureIds",
        "captures": [
            _audio("c1", "یک سی‌سی ژل توی گونه چپ تزریق شد و یک عکس از ناحیه گرفتیم"),
            _photo("ph1", "نمای روبه‌روی گونه چپ"),
        ],
        "expect": {"sectionsNonEmpty": ["treatment-performed"], "noLatinWords": True},
        "judge": True,
    },
    {
        # SAFETY PROPAGATION: a stated allergy must survive into the report and never be negated.
        # Propagation cases test SURFACING only (script-agnostic — a drug name may be written Persian OR
        # Latin/Finglish); romanization is covered by cases 1-4, so no noLatinWords here.
        "name": "allergy dictated → surfaces in report, never negated",
        "captures": [_audio("c1", "یک سی‌سی ژل توی گونه چپ تزریق شد. ضمناً بیمار به لیدوکائین حساسیت داره، حتماً ثبت بشه")],
        "expect": {
            "surfacesAny": [["لیدوکائین", "lidocaine"], ["حساسیت", "آلرژی", "allerg"]],
            "forbiddenAnywhere": ["بدون حساسیت", "حساسیتی ندارد", "حساسیت ندارد", "بدون آلرژی"],
        },
        "judge": True,
    },
    {
        "name": "anticoagulant contraindication surfaces (bleeding risk)",
        "captures": [_audio("c1", "بیست واحد بوتاکس روی پیشانی. توجه بشه که بیمار وارفارین مصرف می‌کنه")],
        "expect": {"surfacesAny": [["وارفارین", "warfarin", "ضد انعقاد", "anticoag"]]},
        "judge": True,
    },
    {
        "name": "adverse event during visit surfaces (not dropped)",
        "captures": [_audio("c1", "یک سی‌سی فیلر لب زدم. بعد از تزریق کبودی و تورم زیادی ایجاد شد که باید پیگیری بشه")],
        "expect": {"surfacesAny": [["کبودی", "تورم", "عารضه", "واکنش", "bruis", "swell"]]},
        "judge": True,
    },
    {
        # LATERALITY fidelity: only the LEFT cheek was treated — the report must not say right.
        "name": "laterality preserved (left only — report must not say right)",
        "captures": [_audio("c1", "یک سی‌سی ژل فقط توی گونه چپ تزریق شد، سمت راست هیچی نزدم")],
        "expect": {"sectionsNonEmpty": ["treatment-performed"], "noLatinWords": True, "surfacesAny": [["چپ"]]},
        "judge": True,
    },
    {
        # MULTI-PHOTO: three real photos (one a product label) — every image block must reference a real
        # captureId AT MOST ONCE (no duplicate refs, no ghosts). `allowLatin` admits the product lot code.
        "name": "multi-photo visit → each real photo referenced at most once, no ghosts",
        "captures": [
            _audio("c1", "دو سی‌سی فیلر توی گونه راست و چپ تزریق شد و از هر دو طرف عکس گرفتیم"),
            _photo("ph1", "نمای روبه‌روی گونه راست"),
            _photo("ph2", "نمای روبه‌روی گونه چپ"),
            _photo("ph3", "برچسب محصول: ژل هیالورونیک اسید، شماره سری ABC123"),
        ],
        "expect": {
            "sectionsNonEmpty": ["treatment-performed"],
            "noLatinWords": True,
            "allowLatin": ["ABC123"],
            "imageRefsUnique": True,
        },
        "judge": True,
    },
    {
        # CROSS-CAPTURE CORRECTION: the dose is dictated (۲۰) then corrected in a later capture (۲۴). The
        # prose must state the FINAL dose only. 20 is not a substring of 24, so the digit tokens don't
        # collide under the tolerant matcher.
        "name": "cross-capture dose correction → prose states the final dose only",
        "captures": [
            _audio("c1", "بیست واحد بوتاکس روی پیشانی تزریق شد"),
            _audio("c2", "ببخشید، دوز درست بیست و چهار واحد شد، همون بیست و چهار واحد ثبت بشه"),
        ],
        "expect": {
            "sectionsNonEmpty": ["treatment-performed"],
            # The corrected dose may legitimately render in digits OR words in Persian prose.
            "containsAnyFa": ["۲۴", "24", "بیست و چهار"],
            "forbiddenAnywhere": ["۲۰ واحد", "بیست واحد"],
        },
        "judge": True,
    },
    {
        # EN report language: English prose is Latin by design, so NO noLatinWords here. Assert English
        # content via surfacesAny (the tolerant substring check) + key sections non-empty. `judge` is off
        # because the judge's nativeScript rubric assumes Persian script and would spuriously penalize
        # legitimately-English prose graded against a Farsi reference.
        "name": "en report language → English prose, key sections complete",
        "language": "en",
        "captures": [_audio("c1", "بیست واحد بوتاکس روی پیشانی و یک سی‌سی ژل توی گونه چپ تزریق شد")],
        "expect": {
            "sectionsNonEmpty": ["visit-summary", "treatment-performed"],
            "surfacesAny": [["botox", "botulinum"], ["forehead"], ["cheek"]],
        },
        "judge": False,
    },
    {
        # META-SPEECH EXCLUSION (S-F13): a capture interleaves clinical dictation with an administrative
        # instruction to staff/the app. The clinical substance must surface; the admin/meta words must
        # NOT leak into the report anywhere (summary, sections, or uncertainties — _report_text spans all).
        "name": "mixed clinical + admin instruction → clinical surfaces, meta-speech excluded",
        "captures": [_audio("c1", "بیست واحد بوتاکس روی پیشانی تزریق شد. راستی این رو برای منشی بفرست و بگو نوبت بعدی رو توی سیستم ثبت کنه")],
        "expect": {
            "sectionsNonEmpty": ["treatment-performed"],
            "surfacesAny": [["بوتاکس", "botox"]],
            "forbiddenAnywhere": ["منشی", "بفرست", "ثبت کنه"],
        },
        "judge": True,
    },
    {
        # META-SPEECH EXCLUSION (S-F13): a SECOND capture is entirely an app command — none of it is
        # clinical, so nothing from it may appear in the report; the clinical capture still surfaces.
        "name": "entirely-meta capture dropped → app commands never appear in the report",
        "captures": [
            _audio("c1", "یک سی‌سی ژل توی گونه چپ تزریق شد"),
            _audio("c2", "ضبط رو نگه دار و فایل ویزیت قبلی رو از سیستم پاک کن"),
        ],
        "expect": {
            "surfacesAny": [["گونه", "cheek"]],
            "forbiddenAnywhere": ["ضبط", "پاک کن", "سیستم"],
        },
        "judge": True,
    },
    {
        # LONG VISIT: a realistically long multi-treatment visit (5 audio captures + a photo). Completeness
        # — the key sections carry content and the several treated areas all surface in the report.
        "name": "long multi-treatment visit (5+ captures) → key sections complete, areas surface",
        "captures": [
            _audio("c1", "بیست واحد بوتاکس روی پیشانی تزریق شد"),
            _audio("c2", "یک سی‌سی ژل توی گونه چپ تزریق شد"),
            _audio("c3", "نیم سی‌سی فیلر توی خط خنده سمت راست"),
            _audio("c4", "مزوتراپی موی سر هم انجام شد"),
            _audio("c5", "برای لب پایین هم نیم سی‌سی فیلر تزریق شد"),
            _photo("ph1", "نمای روبه‌روی صورت بعد از تزریق"),
        ],
        "expect": {
            "sectionsNonEmpty": ["visit-summary", "treatment-performed"],
            "noLatinWords": True,
            "surfacesAny": [["پیشانی"], ["گونه"], ["لب"]],
            "imageRefsUnique": True,
        },
        "judge": True,
    },
]


# --- Runners --------------------------------------------------------------------------------------


def run_gate_self_tests() -> bool:
    print("--- safety-gate self-tests (deterministic, no gateway) ---")
    ok = True
    for index, case in enumerate(GATE_SELF_TESTS, start=1):
        problems = run_gates(case["output"], case["expect"], case["photo_ids"])
        passed = not problems
        as_expected = passed == case["expectGatesPass"]
        if as_expected and not case["expectGatesPass"]:
            needle = case.get("expectReasonContains")
            if needle and not any(needle in problem for problem in problems):
                as_expected = False
        ok = ok and as_expected
        detail = "gates pass" if passed else f"gates fail: {'; '.join(problems)}"
        print(f"  [{index}] {'OK  ' if as_expected else 'BUG '} {case['name']}  → {detail}")
    print(f"  self-tests: {'all matchers behave correctly' if ok else 'HARNESS BUG — a matcher misbehaved'}")
    return ok


def run_cases() -> tuple[int, int, int, int, str | None]:
    """Run the synthetic-transcript synthesis cases on the gateway.

    Returns ``(s_pass, s_fail, q_pass, q_fail, prompt_version)`` — ``prompt_version`` is the first
    output's prompt-version stamp if any output carried one (see ``capture_prompt_version``), else None.
    """
    print("\n--- synthesis cases (synthetic transcripts → gateway) ---")
    safety_pass = safety_fail = quality_pass = quality_fail = 0
    prompt_version: str | None = None
    for index, case in enumerate(CASES, start=1):
        photo_ids = {c["captureId"] for c in case["captures"] if c["type"] == "photo"}

        def _attempt(case=case, photo_ids=photo_ids):
            out = synthesize_session_report(_payload(case["captures"], case.get("language", "fa")))
            if out is None:
                return ["synthesis returned no usable output"], None
            return run_gates(out, case["expect"], photo_ids), out

        try:
            problems, output, attempts = gate_votes(_attempt)
        except Exception as exc:  # noqa: BLE001 — gateway/network: report and stop.
            print(f"  [{index}] ERROR {case['name']}: synthesis failed: {exc!r}")
            print("  SKIP: gateway unreachable — cases not scored.")
            break
        prompt_version = prompt_version or (capture_prompt_version(output) if output else None)
        votes_suffix = f"  [votes:{attempts}/{EVAL_VOTES}]" if attempts > 1 else ""

        non_empty = [s["id"] for s in ((output or {}).get("sections") or []) if s.get("blocks")]
        if problems:
            safety_fail += 1
            print(f"  [{index}] SAFETY FAIL {case['name']}: {'; '.join(problems)}  | non-empty={non_empty}{votes_suffix}")
        else:
            safety_pass += 1
            print(f"  [{index}] SAFETY PASS {case['name']}  → non-empty sections={non_empty}{votes_suffix}")

        # Judge tier stays OUTSIDE the vote (advisory, never re-voted) — once, on the final output.
        if case.get("judge") and output is not None:
            reference = "\n".join(
                c.get("transcript") or c.get("caption") or "" for c in case["captures"]
            )
            try:
                result = judge_sections(reference, _prose(output), list(JUDGE_DIMENSIONS))
            except Exception as exc:  # noqa: BLE001
                print(f"             QUALITY SKIP: judge unreachable: {exc!r}")
                continue
            if not result.get("ok"):
                print(f"             QUALITY WARN: {result.get('rationale')}")
                continue
            if min_score(result["scores"]) >= DEFAULT_MIN_SCORE:
                quality_pass += 1
                tag = "QUALITY PASS"
            else:
                quality_fail += 1
                tag = "QUALITY FAIL"
            print(f"             {tag} ({quality_line(result['scores'], DEFAULT_MIN_SCORE)}) — {result.get('rationale')}")
    return safety_pass, safety_fail, quality_pass, quality_fail, prompt_version


def main() -> int:
    models = env_models("AI_ENGINE_REPORT_SYNTHESIS_MODEL", "AI_ENGINE_TRANSCRIPTION_MODEL")
    self_tests_ok = run_gate_self_tests()
    if not gateway_configured():
        print("\nSKIP: no AI gateway configured. Synthesis cases not run; deterministic self-tests above stand.")
        write_scorecard(
            "report_sections_eval",
            metrics={"self_tests_ok": int(self_tests_ok), "safety_pass": 0, "safety_fail": 0,
                     "quality_pass": 0, "quality_fail": 0, "cases_total": 0},
            models_under_test=models,
        )
        return 0 if self_tests_ok else 1

    safety_pass, safety_fail, quality_pass, quality_fail, prompt_version = run_cases()

    print(f"\n{'=' * 8} REPORT-SECTIONS SCORECARD {'=' * 8}")
    print(f"  self-tests:    {'PASS' if self_tests_ok else 'FAIL (harness bug)'}")
    print(f"  safety gates:  {safety_pass} pass / {safety_fail} fail")
    print(f"  quality (judge): {quality_pass} pass / {quality_fail} below threshold  "
          f"({'blocking' if STRICT_QUALITY else 'advisory'})")
    write_scorecard(
        "report_sections_eval",
        metrics={"self_tests_ok": int(self_tests_ok), "safety_pass": safety_pass, "safety_fail": safety_fail,
                 "quality_pass": quality_pass, "quality_fail": quality_fail,
                 "cases_total": safety_pass + safety_fail},
        models_under_test=models,
        prompt_version=prompt_version,
    )
    return exit_code(self_tests_ok=self_tests_ok, safety_fail=safety_fail, quality_fail=quality_fail)


if __name__ == "__main__":
    raise SystemExit(main())
