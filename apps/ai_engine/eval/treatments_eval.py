#!/usr/bin/env python3
"""Minimal Farsi golden-set eval for Pro treatment extraction (the clinical-trust gate).

Opt-in eval that runs the real single-pass synthesis (``synthesize_session_report``) against the
configured gateway over ~12 real-style Farsi dictation cases — corrections, additions, carry-forward,
lot-on-label — and asserts the extracted ``treatments[]`` CORE fields. It reports pass/fail per case.

Run it where a gateway is reachable::

    docker exec notari_build_<stack>-ai-engine-1 python /app/eval/treatments_eval.py
    # or locally, with AI_ENGINE_TRANSCRIPTION_BASE_URL / *_MODEL pointing at an OpenAI-compatible gateway

No gateway configured/reachable → the script SKIPS (exit 0) and says so; it never blocks CI. With a
gateway it exits non-zero if any case fails, so it can gate "dose extraction is trusted clinically".

The deterministic correction/carry-forward/supersede POST-processing is unit-tested separately
(backend ``tests/test_treatment_synthesis.py`` + ai_engine ``tests/test_report_synthesis.py``); this
eval measures the LLM extraction itself, which the unit tests cannot.
"""
from __future__ import annotations

import re
import sys
from typing import Any

# A Persian report's DESCRIPTIVE treatment fields (area/product/unit) must be in Persian script, not
# an English category like "filler"/"botox"/"unit". Brand/lot/quantityText stay verbatim (not checked).
PERSIAN_RE = re.compile(r"[؀-ۿ]")
LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")

# Allow running as a bare script (python eval/treatments_eval.py) from the ai_engine package root.
sys.path.insert(0, ".")
sys.path.insert(0, "/app")

from ai_engine.processing import synthesize_session_report, transcription_is_configured  # noqa: E402

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
        "expect": {"count": 1, "items": [{"product": ["ژل", "gel", "juvederm", "ژوویدرم"], "lot_present": True}]},
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
    """Return a list of failure reasons (empty = the item matched)."""
    problems: list[str] = []
    product_text = f"{_norm(actual.get('product'))} {_norm(actual.get('brand'))} {_norm(actual.get('area'))} {_norm(actual.get('quantityText'))}"
    if "product" in expected and not any(_norm(token) in product_text for token in expected["product"]):
        problems.append(f"product≈{expected['product']} not in {product_text!r}")
    if "quantity" in expected and actual.get("quantity") != expected["quantity"]:
        problems.append(f"quantity {actual.get('quantity')}≠{expected['quantity']}")
    if "unit" in expected and not any(_norm(token) in _norm(actual.get("unit")) or _norm(token) in _norm(actual.get("quantityText")) for token in expected["unit"]):
        problems.append(f"unit≈{expected['unit']} not in {actual.get('unit')!r}/{actual.get('quantityText')!r}")
    if expected.get("lot_present") and not actual.get("lot"):
        problems.append("lot expected but missing")
    return problems


def _check(case: dict[str, Any], output: dict[str, Any]) -> tuple[bool, list[str]]:
    treatments = output.get("treatments") or []
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
    # Greedily match each expected item to some actual treatment.
    for expected_item in expect.get("items", []):
        if not any(not _match_item(actual, expected_item) for actual in treatments):
            notes.append(f"no treatment matched {expected_item}")
    return (not notes), notes


def main() -> int:
    if not transcription_is_configured():
        print("SKIP: no AI gateway configured (AI_ENGINE_TRANSCRIPTION_BASE_URL empty). Golden-set eval needs a gateway.")
        return 0
    passed = 0
    failed = 0
    for index, case in enumerate(CASES, start=1):
        try:
            output = synthesize_session_report(_payload(case["captures"], case.get("prior")))
        except Exception as exc:  # gateway/network error — report and stop (can't eval without it).
            print(f"ERROR: gateway call failed on case {index} ({case['name']}): {exc!r}")
            print("SKIP: gateway unreachable — eval not run. Re-run where the synthesis gateway is reachable.")
            return 0
        if output is None:
            print(f"[{index:2}] FAIL  {case['name']}: synthesis returned no usable output (malformed/empty)")
            failed += 1
            continue
        ok, notes = _check(case, output)
        treatments = output.get("treatments") or []
        summary = "; ".join(
            f"{t.get('product')}/{t.get('quantityText') or t.get('quantity')}{'(cf)' if t.get('carriedForward') else ''}{'(sup)' if t.get('supersedesCaptureId') else ''}"
            for t in treatments
        )
        if ok:
            print(f"[{index:2}] PASS  {case['name']}  → {summary or '(no treatments)'}")
            passed += 1
        else:
            print(f"[{index:2}] FAIL  {case['name']}  → {summary or '(no treatments)'}  | {', '.join(notes)}")
            failed += 1
    total = passed + failed
    print(f"\nGolden set: {passed}/{total} passed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
