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
    AUDIO_SUFFIXES,
    capture_prompt_version,
    contains,
    env_models,
    exit_code,
    gateway_configured,
    load_fixtures,
    number_tokens,
    write_scorecard,
)
from ai_engine.processing import (  # noqa: E402
    synthesize_session_report,
    transcribe_audio_content,
)

# A Persian report's DESCRIPTIVE treatment fields (area/product/unit) must be in Persian script, not
# an English category like "filler"/"botox"/"unit". Brand/lot/quantityText stay verbatim (not checked).
PERSIAN_RE = re.compile(r"[؀-ۿ]")
LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")

DOMAIN = {
    "label": "aesthetics clinic",
    "vocabulary": ["filler", "Botox", "ژل", "بوتاکس", "کانولا", "واحد", "سی‌سی"],
}

# The demo clinic's aftercare protocols (mirror aftercare_conflict_eval) — the synthesis-fixture path
# below scores treatments AND aftercare on one real clip, so it needs them in the payload.
AFTERCARE_TEMPLATES = [
    {"id": "tmpl-botox", "name": "مراقبت بعد از بوتاکس", "procedureType": "botox",
     "body": "تا ۴ ساعت دراز نکشید. ۲۴ ساعت ورزش سنگین و ماساژ ناحیه ممنوع. تا ۳ روز از سونا و آفتاب مستقیم پرهیز کنید."},
    {"id": "tmpl-filler", "name": "مراقبت بعد از فیلر", "procedureType": "filler",
     "body": "تا ۲۴ ساعت آرایش نکنید. کمپرس سرد برای کاهش تورم. تا ۲ هفته از حرارت زیاد (سونا/سولاریوم) پرهیز کنید."},
]

# Aesthetics framing for transcribing a synthesis fixture clip (mirrors the transcription eval).
TRANSCRIPTION_FIXTURE_CONTEXT = {"preferredLanguage": "auto", "domain": DOMAIN}


def _audio(capture_id: str, transcript: str) -> dict[str, Any]:
    return {"captureId": capture_id, "type": "audio", "transcript": transcript}


def _payload(
    captures: list[dict[str, Any]],
    prior_treatments: list[dict[str, Any]] | None = None,
    aftercare_templates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "job": {"id": "eval-job", "jobType": "session_organize"},
        "session": {"reportTemplateKey": "default"},
        "reportTemplate": {"key": "default"},
        "aiModels": {},
        "sessionProcessingContext": {
            "domain": DOMAIN,
            "reportLanguage": "fa",
            "aftercareTemplates": aftercare_templates or [],
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
    # --- (a) Distractor / negative classes: mentioned-but-not-done must NOT become a treatment. ------
    {
        "name": "future plan only — nothing performed (dafe baad)",
        "captures": [_audio("c1", "امروز کاری نکردیم، فقط گفتم دفعه بعد دو سی‌سی فیلر گونه می‌زنیم")],
        "expect": {"count": 0, "items": []},
    },
    {
        "name": "performed + future plan — extract only the performed dose (plan is a distractor)",
        "captures": [_audio("c1", "بیست واحد بوتاکس روی پیشونی زدم. دفعه بعد دو سی‌سی فیلر لب هم می‌زنیم")],
        "expect": {"count": 1, "items": [{"product": ["بوتاکس", "botox"], "quantity": 20}], "forbiddenQuantity": [2]},
    },
    {
        "name": "prior-visit recall only — not performed this visit",
        "captures": [_audio("c1", "دفعه قبل یک سی‌سی ژل توی گونه زده بودیم. امروز فقط معاینه کردم، چیزی تزریق نشد")],
        "expect": {"count": 0, "items": []},
    },
    {
        "name": "declined by patient — offered but not done",
        "captures": [_audio("c1", "به بیمار پیشنهاد یک سی‌سی فیلر لب دادم ولی قبول نکرد و انجام نشد")],
        "expect": {"count": 0, "items": [], "forbiddenQuantity": [1]},
    },
    # --- (b) Multi-capture: production sessions are split across captures; a later capture corrects. --
    {
        "name": "multi-capture correction — capture 2 fixes capture 1's dose",
        "captures": [
            _audio("c1", "دو سی‌سی ژل توی گونه چپ تزریق شد"),
            _audio("c2", "ببخشید اشتباه گفتم، سه سی‌سی شد نه دو سی‌سی"),
        ],
        "expect": {"count": 1, "items": [{"product": ["ژل", "gel"], "quantity": 3}], "supersede": True, "forbiddenQuantity": [2]},
    },
    {
        "name": "multi-capture addition — second capture adds a distinct product",
        "captures": [
            _audio("c1", "بیست واحد بوتاکس روی پیشونی زدم"),
            _audio("c2", "بعدش یک سی‌سی ژل هم توی گونه چپ تزریق کردم"),
        ],
        "expect": {"count": 2, "items": [{"product": ["بوتاکس", "botox"]}, {"product": ["ژل", "gel"]}]},
    },
    # --- (c) Structured-field exact-match: quantityText is the verbatim trust anchor. ----------------
    {
        "name": "quantityText verbatim (structured exact-match trust anchor)",
        "captures": [_audio("c1", "بیست و چهار واحد بوتاکس روی پیشونی زدم")],
        "lang_fa": True,
        "expect": {"count": 1, "items": [{"product": ["بوتاکس", "botox"], "quantity": 24, "quantityTextContains": ["۲۴", "24"]}]},
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
    # The trust anchor: `quantityText` is the verbatim dose string shown to the clinician, so a structured
    # exact-match case asserts each token appears in it verbatim (tolerant only for ZWNJ/digit folding).
    for token in expected.get("quantityTextContains", []):
        if not contains(actual.get("quantityText"), token):
            problems.append(f"quantityText {token!r} not verbatim in {actual.get('quantityText')!r}")
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
    # Distractor guard: a dose that was only PLANNED / recalled from a prior visit / declined must not
    # be extracted as a performed treatment. Each forbidden value must not appear as any treatment's
    # quantity (nor verbatim in its quantityText).
    for value in expect.get("forbiddenQuantity", []):
        token = str(value).rstrip("0").rstrip(".") if isinstance(value, float) else str(value)
        if any(
            t.get("quantity") == value or token in number_tokens(str(t.get("quantityText") or ""))
            for t in treatments
        ):
            notes.append(f"distractor dose {value} extracted as a performed treatment (plan/history/declined)")
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
    {
        "name": "verbatim quantityText PASSES the exact-match anchor",
        "output": _output([{"product": "بوتاکس", "quantity": 24, "unit": "واحد", "quantityText": "۲۴ واحد"}]),
        "case": {"expect": {"count": 1, "items": [{"product": ["بوتاکس"], "quantityTextContains": ["24"]}]}},
        "expectGatesPass": True,
    },
    {
        "name": "wrong quantityText FAILS the exact-match anchor",
        "output": _output([{"product": "بوتاکس", "quantity": 24, "unit": "واحد", "quantityText": "۲۰ واحد"}]),
        "case": {"expect": {"count": 1, "items": [{"product": ["بوتاکس"], "quantityTextContains": ["24"]}]}},
        "expectGatesPass": False,
        "expectReasonContains": "quantityText",
    },
    {
        "name": "extracted distractor dose FAILS the forbiddenQuantity guard",
        "output": _output([{"product": "فیلر", "quantity": 2, "unit": "سی‌سی", "quantityText": "۲ سی‌سی"}]),
        "case": {"expect": {"count_min": 0, "items": [], "forbiddenQuantity": [2]}},
        "expectGatesPass": False,
        "expectReasonContains": "distractor dose",
    },
    {
        "name": "no distractor extracted PASSES the forbiddenQuantity guard",
        "output": _output([{"product": "بوتاکس", "quantity": 20, "unit": "واحد", "quantityText": "۲۰ واحد"}]),
        "case": {"expect": {"count": 1, "items": [{"product": ["بوتاکس"], "quantity": 20}], "forbiddenQuantity": [2]}},
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


def run_cases() -> tuple[int, int, int, list[dict[str, Any]], str | None]:
    """Run the synthetic Farsi dictation cases on the gateway. Returns (pass, fail, known_gap, records, prompt_version)."""
    print("\n--- treatment extraction cases (synthetic Farsi dictations → gateway) ---")
    safety_pass = safety_fail = known_gap = 0
    records: list[dict[str, Any]] = []
    prompt_version: str | None = None
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
        prompt_version = prompt_version or capture_prompt_version(output)
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
    return safety_pass, safety_fail, known_gap, records, prompt_version


def _aftercare_status_ok(expected: str, actual: str | None) -> bool:
    """Mirror aftercare_conflict_eval: 'applies' is exact; 'flag' accepts conflicts OR superseded."""
    if expected == "applies":
        return actual == "applies"
    return actual in ("conflicts", "superseded")


def run_synthesis_fixtures() -> tuple[int, int, int, list[dict[str, Any]], str | None]:
    """The #3d real-clip path: transcribe a full-visit clip → synthesize → gate treatments + aftercare.

    Closes the loop the recording checklist opened: ``fixtures/synthesis/s0N-*.m4a`` + a sibling
    ``.json`` (``said`` reference, a ``treatments`` expect block in the ``CASES`` shape, and an optional
    ``aftercare`` map ``{templateId: "applies"|"flag"}``) is scored end-to-end on the REAL pipeline —
    the "real noisy carried-forward session" lesson synthetic text can't reproduce. Until a clip lands
    this finds nothing and no-ops. Returns (pass, fail, known_gap, records, prompt_version).
    """
    fixtures = load_fixtures("synthesis", AUDIO_SUFFIXES)
    print("\n--- full-visit synthesis fixtures (real clip → transcribe → synthesize) ---")
    if not fixtures:
        print("  (no clips yet — record s01–s04 per the checklist to score treatments+aftercare on real audio)")
        return 0, 0, 0, [], None
    safety_pass = safety_fail = known_gap = 0
    records: list[dict[str, Any]] = []
    prompt_version: str | None = None
    for index, fixture in enumerate(fixtures, start=1):
        name, spec = fixture["name"], fixture.get("spec")
        if spec is None:
            print(f"  [{index}] SKIP {name}: {fixture.get('error', 'no sibling .json with expected facts')}")
            continue
        try:
            transcription = transcribe_audio_content(fixture["media"].read_bytes(), {**TRANSCRIPTION_FIXTURE_CONTEXT})
            transcript = (transcription or {}).get("transcript") or ""
            output = synthesize_session_report(_payload([_audio("s1", transcript)], aftercare_templates=AFTERCARE_TEMPLATES))
        except Exception as exc:  # noqa: BLE001 — gateway/ffmpeg error: report and stop scoring fixtures.
            print(f"  [{index}] ERROR {name}: transcribe/synthesize failed: {exc!r}")
            print("  SKIP: gateway/ffmpeg unreachable — synthesis fixtures not scored.")
            break
        if output is None:
            print(f"  [{index}] SAFETY FAIL {name}: synthesis returned no usable output")
            safety_fail += 1
            records.append({"id": name, "safety": "fail", "judge": {}, "reasons": ["no usable output"]})
            continue
        prompt_version = prompt_version or capture_prompt_version(output)

        problems: list[str] = []
        if spec.get("treatments"):
            problems.extend(run_gates(output, {"expect": spec["treatments"], "lang_fa": spec.get("lang_fa")}))
        by_id = {s.get("templateId"): s.get("status") for s in (output.get("aftercareSelections") or []) if isinstance(s, dict)}
        for template_id, expected_status in (spec.get("aftercare") or {}).items():
            actual = by_id.get(template_id)
            if actual is None:
                problems.append(f"aftercare {template_id}: MISSING (expected {expected_status})")
            elif not _aftercare_status_ok(expected_status, actual):
                problems.append(f"aftercare {template_id}: {actual}≠{expected_status}")

        summary = "; ".join(f"{t.get('product')}/{t.get('quantityText') or t.get('quantity')}" for t in (output.get("treatments") or [])) or "(no treatments)"
        known = spec.get("knownGap")
        if problems and known:
            known_gap += 1
            print(f"  [{index}] KNOWN-GAP {name}: {', '.join(problems)}  → {summary}\n             ↳ {known}")
            records.append({"id": name, "safety": "known-gap", "judge": {}, "reasons": problems})
        elif problems:
            safety_fail += 1
            print(f"  [{index}] SAFETY FAIL {name}  → {summary}  | {', '.join(problems)}")
            records.append({"id": name, "safety": "fail", "judge": {}, "reasons": problems})
        else:
            safety_pass += 1
            print(f"  [{index}] SAFETY PASS {name}  → {summary}")
            records.append({"id": name, "safety": "pass", "judge": {}, "reasons": []})
    return safety_pass, safety_fail, known_gap, records, prompt_version


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

    safety_pass, safety_fail, known_gap, records, prompt_version = run_cases()
    fx_pass, fx_fail, fx_known, fx_records, fx_prompt_version = run_synthesis_fixtures()
    safety_pass += fx_pass
    safety_fail += fx_fail
    known_gap += fx_known
    records.extend(fx_records)
    prompt_version = prompt_version or fx_prompt_version

    print(f"\n{'=' * 8} TREATMENTS SCORECARD {'=' * 8}")
    print(f"  self-tests:    {'PASS' if self_tests_ok else 'FAIL (harness bug)'}")
    print(f"  safety gates:  {safety_pass} pass / {safety_fail} fail / {known_gap} known-gap  (incl. synthesis fixtures)")
    write_scorecard(
        "treatments_eval",
        metrics={
            "self_tests_ok": int(self_tests_ok), "safety_pass": safety_pass, "safety_fail": safety_fail,
            "known_gap": known_gap, "cases_total": safety_pass + safety_fail + known_gap,
        },
        cases=records,
        models_under_test=env_models("AI_ENGINE_REPORT_SYNTHESIS_MODEL", "AI_ENGINE_TRANSCRIPTION_MODEL"),
        prompt_version=prompt_version,
    )
    return exit_code(self_tests_ok=self_tests_ok, safety_fail=safety_fail)


if __name__ == "__main__":
    raise SystemExit(main())
