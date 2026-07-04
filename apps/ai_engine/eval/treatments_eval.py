#!/usr/bin/env python3
"""Farsi golden-set eval for Pro treatment extraction (the clinical-trust gate).

Runs the real single-pass synthesis (``synthesize_session_report``) against the configured gateway over
~12 real-style Farsi dictation cases — corrections, additions, carry-forward, lot-on-label — and asserts
the extracted ``treatments[]`` CORE fields. Shares the two-tier harness in ``_common.py`` (tolerant
Persian matching, ``knownGap`` xfail, the exit-code policy, and the machine-readable scorecard):

* **Safety gates** — deterministic matchers over the treatments array. HARD pass/fail.

Run it where a gateway is reachable::

    docker exec engram-main-ai-engine-1 python /app/eval/treatments_eval.py

No gateway → the gateway cases SKIP; deterministic gate self-tests still run. Exit is SAFETY only.

The deterministic correction/carry-forward/supersede POST-processing is unit-tested separately
(backend ``tests/test_treatment_synthesis.py`` + ai_engine ``tests/test_report_synthesis.py``); this
eval measures the LLM extraction itself, which the unit tests cannot.
"""
from __future__ import annotations

import pathlib
import re
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
    contains,
    env_models,
    exit_code,
    gateway_configured,
    write_scorecard,
)
from ai_engine.processing import synthesize_session_report  # noqa: E402

# A Persian report's DESCRIPTIVE treatment fields (area/product/unit) must be in Persian script, not
# an English category like "filler"/"botox"/"unit". Brand/lot/quantityText stay verbatim (not checked).
PERSIAN_RE = re.compile(r"[؀-ۿ]")
LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")

DOMAIN = {
    "label": "aesthetics clinic",
    "vocabulary": ["filler", "Botox", "ژل", "بوتاکس", "کانولا", "واحد", "سی‌سی"],
}


def _audio(capture_id: str, transcript: str) -> dict[str, Any]:
    return {"captureId": capture_id, "type": "audio", "transcript": transcript}


def _payload(captures: list[dict[str, Any]], prior_treatments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
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
            "referencePriorVisitTreatments": prior_treatments or [],
        },
    }


# ~12 real-style Farsi dictation cases with expected treatments[] CORE fields. Matchers are tolerant
# (substring / numeric equality) because the LLM phrasing varies; the clinical facts must hold.
CASES: list[dict[str, Any]] = [
    {
        "name": "single filler injection",
        "captures": [_audio("c1", "دو سی‌سی ژل توی گونه چپ تزریق شد")],
        "lang_fa": True,
        "expect": {"count": 1, "items": [{"product": ["ژل", "gel", "filler"], "quantity": 2, "unit": ["cc", "سی‌سی", "ml"]}]},
    },
    {
        "name": "botox units forehead",
        "captures": [_audio("c1", "بیست واحد بوتاکس روی پیشونی زدیم")],
        "lang_fa": True,
        "expect": {"count": 1, "items": [{"product": ["بوتاکس", "botox"], "quantity": 20, "unit": ["unit", "واحد"]}]},
    },
    {
        "name": "correction same area (eshtebah goftam)",
        "captures": [_audio("c1", "گونه چپ دو سی‌سی ژل ... نه اشتباه گفتم، سه سی‌سی ژل توی گونه چپ")],
        "expect": {"count": 1, "items": [{"product": ["ژل", "gel"], "quantity": 3, "unit": ["cc", "سی‌سی"]}], "supersede": True},
    },
    {
        "name": "correction (manzooram ... bood)",
        "captures": [_audio("c1", "یک سی‌سی ژل توی لب ... منظورم یک و نیم سی‌سی بود")],
        "expect": {"count": 1, "items": [{"product": ["ژل", "gel"], "quantity": 1.5}], "supersede": True},
    },
    {
        "name": "addition two areas (ham ... ham)",
        "captures": [_audio("c1", "هم گونه چپ هم گونه راست، هرکدوم یک سی‌سی ژل تزریق شد")],
        "expect": {"count": 2, "items": [{"product": ["ژل", "gel"]}, {"product": ["ژل", "gel"]}]},
    },
    {
        "name": "two distinct products",
        "captures": [_audio("c1", "یک سی‌سی ژل توی لب و ده واحد بوتاکس روی اخم")],
        "lang_fa": True,
        "expect": {"count": 2, "items": [{"product": ["ژل", "gel"]}, {"product": ["بوتاکس", "botox"]}]},
    },
    {
        "name": "carry forward same as last time",
        "captures": [_audio("c1", "بوتاکس پیشونی مثل دفعه قبل، همون مقدار")],
        "prior": [{"area": "forehead", "product": "Botox", "quantity": 20, "unit": "unit", "sourceCaptureIds": ["prev-1"]}],
        "expect": {"count": 1, "items": [{"product": ["بوتاکس", "botox"]}], "carriedForward": True},
    },
    {
        "name": "lot on label (dictated lot)",
        "captures": [_audio("c1", "ژل ژوویدرم با شماره لات A B C یک دو سه تزریق شد")],
        "brand_separated": "ژوویدرم",
        "expect": {"count": 1, "items": [{"product": ["ژل", "gel"], "lot_present": True}]},
    },
    {
        "name": "brand restylane",
        "captures": [_audio("c1", "یک سی‌سی رستیلین توی گونه")],
        "expect": {"count": 1, "items": [{"product": ["رستیلین", "restylane", "ژل", "filler"], "quantity": 1}]},
    },
    {
        "name": "cannula technique attribute",
        "captures": [_audio("c1", "یک سی‌سی ژل با کانولا توی گونه چپ تزریق شد")],
        "expect": {"count": 1, "items": [{"product": ["ژل", "gel"], "quantity": 1}]},
    },
    {
        "name": "consult only — no treatment",
        "captures": [_audio("c1", "فقط مشاوره بود، امروز هیچ تزریقی انجام نشد")],
        "expect": {"count": 0, "items": []},
    },
    {
        "name": "additive top-up same area (ham ezafe)",
        "captures": [_audio("c1", "اول یک سی‌سی ژل زدم بعد نیم سی‌سی دیگه هم اضافه کردم همون گونه")],
        "expect": {"count_min": 1, "items": [{"product": ["ژل", "gel"]}]},
    },
]


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _not_report_language_fa(value: Any) -> bool:
    """True if a descriptive field is NOT in Persian (empty is fine; English word = a violation)."""
    text = str(value or "").strip()
    if not text:
        return False
    return bool(LATIN_WORD_RE.search(text)) or not PERSIAN_RE.search(text)


def _language_problems(treatments: list[dict[str, Any]]) -> list[str]:
    problems: list[str] = []
    for treatment in treatments:
        for field in ("area", "product", "unit"):
            if _not_report_language_fa(treatment.get(field)):
                problems.append(f"{field}={treatment.get(field)!r} not in report language (fa)")
    return problems


def _match_item(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    """Return a list of failure reasons (empty = the item matched). Tolerant Persian matching via
    ``_common.contains`` (ZWNJ/digit/letter-form folding); quantity stays an exact numeric compare."""
    problems: list[str] = []
    product_text = f"{_norm(actual.get('product'))} {_norm(actual.get('brand'))} {_norm(actual.get('area'))} {_norm(actual.get('quantityText'))}"
    if "product" in expected and not any(contains(product_text, token) for token in expected["product"]):
        problems.append(f"product≈{expected['product']} not in {product_text!r}")
    if "quantity" in expected and actual.get("quantity") != expected["quantity"]:
        problems.append(f"quantity {actual.get('quantity')}≠{expected['quantity']}")
    if "unit" in expected and not any(
        contains(actual.get("unit"), token) or contains(actual.get("quantityText"), token) for token in expected["unit"]
    ):
        problems.append(f"unit≈{expected['unit']} not in {actual.get('unit')!r}/{actual.get('quantityText')!r}")
    if expected.get("lot_present") and not actual.get("lot"):
        problems.append("lot expected but missing")
    return problems


def run_gates(output: dict[str, Any], case: dict[str, Any]) -> list[str]:
    """Apply the deterministic treatment gates to a synthesis output; return failures (empty == pass)."""
    treatments = [t for t in (output.get("treatments") or []) if isinstance(t, dict)]
    expect = case["expect"]
    notes: list[str] = []
    if "count" in expect and len(treatments) != expect["count"]:
        notes.append(f"count {len(treatments)}≠{expect['count']}")
    if "count_min" in expect and len(treatments) < expect["count_min"]:
        notes.append(f"count {len(treatments)}<{expect['count_min']}")
    if expect.get("carriedForward") and not any(t.get("carriedForward") for t in treatments):
        notes.append("no carriedForward treatment")
    if expect.get("supersede") and not any(t.get("supersedesCaptureId") for t in treatments):
        notes.append("no supersedesCaptureId set")
    if case.get("lang_fa"):
        notes.extend(_language_problems(treatments))
    brand_token = case.get("brand_separated")
    if brand_token and not any(
        contains(t.get("brand"), brand_token) and not contains(t.get("product"), brand_token) for t in treatments
    ):
        notes.append(f"brand '{brand_token}' not split into the brand field (product leaked it)")
    # Greedily match each expected item to some actual treatment.
    for expected_item in expect.get("items", []):
        if not any(not _match_item(actual, expected_item) for actual in treatments):
            notes.append(f"no treatment matched {expected_item}")
    return notes


# --- Deterministic gate self-tests (synthetic OUTPUT dicts, no gateway) ---------------------------

def _output(treatments: list[dict[str, Any]]) -> dict[str, Any]:
    return {"treatments": treatments}


GATE_SELF_TESTS: list[dict[str, Any]] = [
    {
        "name": "single grounded fa treatment passes",
        "output": _output([{"product": "ژل", "quantity": 2, "unit": "سی‌سی", "area": "گونه چپ"}]),
        "case": {"lang_fa": True, "expect": {"count": 1, "items": [{"product": ["ژل"], "quantity": 2, "unit": ["سی‌سی"]}]}},
        "expectGatesPass": True,
    },
    {
        "name": "wrong count FAILS the count gate",
        "output": _output([{"product": "ژل", "quantity": 2, "unit": "سی‌سی"}]),
        "case": {"expect": {"count": 2, "items": []}},
        "expectGatesPass": False,
        "expectReasonContains": "count",
    },
    {
        "name": "wrong quantity FAILS the item match",
        "output": _output([{"product": "ژل", "quantity": 3, "unit": "سی‌سی"}]),
        "case": {"expect": {"count": 1, "items": [{"product": ["ژل"], "quantity": 2}]}},
        "expectGatesPass": False,
        "expectReasonContains": "no treatment matched",
    },
    {
        "name": "missing carriedForward FAILS",
        "output": _output([{"product": "بوتاکس", "quantity": 20, "unit": "واحد"}]),
        "case": {"expect": {"count": 1, "items": [], "carriedForward": True}},
        "expectGatesPass": False,
        "expectReasonContains": "carriedForward",
    },
    {
        "name": "missing supersede FAILS",
        "output": _output([{"product": "ژل", "quantity": 3, "unit": "سی‌سی"}]),
        "case": {"expect": {"count": 1, "items": [], "supersede": True}},
        "expectGatesPass": False,
        "expectReasonContains": "supersedesCaptureId",
    },
    {
        "name": "English descriptive field FAILS the report-language gate",
        "output": _output([{"product": "filler", "quantity": 2, "unit": "cc", "area": "left cheek"}]),
        "case": {"lang_fa": True, "expect": {"count": 1, "items": []}},
        "expectGatesPass": False,
        "expectReasonContains": "report language",
    },
    {
        "name": "brand leaked into product FAILS the brand-split gate",
        "output": _output([{"product": "ژل ژوویدرم", "brand": "", "quantity": 1, "unit": "سی‌سی"}]),
        "case": {"brand_separated": "ژوویدرم", "expect": {"count": 1, "items": []}},
        "expectGatesPass": False,
        "expectReasonContains": "brand field",
    },
    {
        "name": "brand correctly split PASSES",
        "output": _output([{"product": "ژل", "brand": "ژوویدرم", "quantity": 1, "unit": "سی‌سی", "lot": "ABC123"}]),
        "case": {"brand_separated": "ژوویدرم", "expect": {"count": 1, "items": [{"product": ["ژل"], "lot_present": True}]}},
        "expectGatesPass": True,
    },
    {
        "name": "missing lot FAILS the lot_present item check",
        "output": _output([{"product": "ژل", "quantity": 1, "unit": "سی‌سی"}]),
        "case": {"expect": {"count": 1, "items": [{"product": ["ژل"], "lot_present": True}]}},
        "expectGatesPass": False,
        "expectReasonContains": "no treatment matched",
    },
    {
        "name": "consult-only (zero treatments) PASSES count 0",
        "output": _output([]),
        "case": {"expect": {"count": 0, "items": []}},
        "expectGatesPass": True,
    },
]


# --- Runners --------------------------------------------------------------------------------------


def run_gate_self_tests() -> bool:
    print("--- safety-gate self-tests (deterministic, no gateway) ---")
    ok = True
    for index, case in enumerate(GATE_SELF_TESTS, start=1):
        problems = run_gates(case["output"], case["case"])
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


def run_cases() -> tuple[int, int, int, list[dict[str, Any]]]:
    """Run the synthetic Farsi dictation cases on the gateway. Returns (pass, fail, known_gap, records)."""
    print("\n--- treatment extraction cases (synthetic Farsi dictations → gateway) ---")
    safety_pass = safety_fail = known_gap = 0
    records: list[dict[str, Any]] = []
    for index, case in enumerate(CASES, start=1):
        try:
            output = synthesize_session_report(_payload(case["captures"], case.get("prior")))
        except Exception as exc:  # noqa: BLE001 — gateway/network: report and stop scoring.
            print(f"  [{index}] ERROR {case['name']}: synthesis failed: {exc!r}")
            print("  SKIP: gateway unreachable — remaining cases not scored.")
            break
        if output is None:
            print(f"  [{index}] SAFETY FAIL {case['name']}: synthesis returned no usable output (malformed/empty)")
            safety_fail += 1
            records.append({"id": case["name"], "safety": "fail", "judge": {}, "reasons": ["no usable output"]})
            continue
        problems = run_gates(output, case)
        treatments = output.get("treatments") or []
        summary = "; ".join(
            f"{t.get('product')}/{t.get('quantityText') or t.get('quantity')}{'(cf)' if t.get('carriedForward') else ''}{'(sup)' if t.get('supersedesCaptureId') else ''}"
            for t in treatments
        ) or "(no treatments)"
        known = case.get("knownGap")
        if problems and known:
            known_gap += 1
            print(f"  [{index}] KNOWN-GAP {case['name']}: {', '.join(problems)}  → {summary}\n             ↳ {known}")
            records.append({"id": case["name"], "safety": "known-gap", "judge": {}, "reasons": problems})
        elif problems:
            safety_fail += 1
            print(f"  [{index}] SAFETY FAIL {case['name']}  → {summary}  | {', '.join(problems)}")
            records.append({"id": case["name"], "safety": "fail", "judge": {}, "reasons": problems})
        else:
            safety_pass += 1
            print(f"  [{index}] SAFETY PASS {case['name']}  → {summary}")
            records.append({"id": case["name"], "safety": "pass", "judge": {}, "reasons": []})
    return safety_pass, safety_fail, known_gap, records


def main() -> int:
    self_tests_ok = run_gate_self_tests()
    if not gateway_configured():
        print("\nSKIP: no AI gateway configured. Extraction cases not run; deterministic self-tests above stand.")
        write_scorecard(
            "treatments_eval",
            metrics={"self_tests_ok": int(self_tests_ok), "safety_pass": 0, "safety_fail": 0, "known_gap": 0, "cases_total": 0},
            models_under_test=env_models("AI_ENGINE_REPORT_SYNTHESIS_MODEL", "AI_ENGINE_TRANSCRIPTION_MODEL"),
        )
        return 0 if self_tests_ok else 1

    safety_pass, safety_fail, known_gap, records = run_cases()

    print(f"\n{'=' * 8} TREATMENTS SCORECARD {'=' * 8}")
    print(f"  self-tests:    {'PASS' if self_tests_ok else 'FAIL (harness bug)'}")
    print(f"  safety gates:  {safety_pass} pass / {safety_fail} fail / {known_gap} known-gap")
    write_scorecard(
        "treatments_eval",
        metrics={
            "self_tests_ok": int(self_tests_ok), "safety_pass": safety_pass, "safety_fail": safety_fail,
            "known_gap": known_gap, "cases_total": safety_pass + safety_fail + known_gap,
        },
        cases=records,
        models_under_test=env_models("AI_ENGINE_REPORT_SYNTHESIS_MODEL", "AI_ENGINE_TRANSCRIPTION_MODEL"),
    )
    return exit_code(self_tests_ok=self_tests_ok, safety_fail=safety_fail)


if __name__ == "__main__":
    raise SystemExit(main())
