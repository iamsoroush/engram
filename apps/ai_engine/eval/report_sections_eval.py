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
    STRICT_QUALITY,
    contains,
    env_models,
    exit_code,
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


def _payload(captures: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "job": {"id": "eval-job", "jobType": "session_organize"},
        "session": {"reportTemplateKey": "default"},
        "reportTemplate": {"key": "default"},
        "aiModels": {},
        "sessionProcessingContext": {
            "domain": DOMAIN,
            "reportLanguage": "fa",
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


def run_cases() -> tuple[int, int, int, int]:
    """Run the synthetic-transcript synthesis cases on the gateway. Returns (s_pass, s_fail, q_pass, q_fail)."""
    print("\n--- synthesis cases (synthetic transcripts → gateway) ---")
    safety_pass = safety_fail = quality_pass = quality_fail = 0
    for index, case in enumerate(CASES, start=1):
        photo_ids = {c["captureId"] for c in case["captures"] if c["type"] == "photo"}
        try:
            output = synthesize_session_report(_payload(case["captures"]))
        except Exception as exc:  # noqa: BLE001 — gateway/network: report and stop.
            print(f"  [{index}] ERROR {case['name']}: synthesis failed: {exc!r}")
            print("  SKIP: gateway unreachable — cases not scored.")
            break
        if output is None:
            print(f"  [{index}] SAFETY FAIL {case['name']}: synthesis returned no usable output")
            safety_fail += 1
            continue

        problems = run_gates(output, case["expect"], photo_ids)
        non_empty = [s["id"] for s in output["sections"] if s.get("blocks")]
        if problems:
            safety_fail += 1
            print(f"  [{index}] SAFETY FAIL {case['name']}: {'; '.join(problems)}  | non-empty={non_empty}")
        else:
            safety_pass += 1
            print(f"  [{index}] SAFETY PASS {case['name']}  → non-empty sections={non_empty}")

        if case.get("judge"):
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
    return safety_pass, safety_fail, quality_pass, quality_fail


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

    safety_pass, safety_fail, quality_pass, quality_fail = run_cases()

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
    )
    return exit_code(self_tests_ok=self_tests_ok, safety_fail=safety_fail, quality_fail=quality_fail)


if __name__ == "__main__":
    raise SystemExit(main())
