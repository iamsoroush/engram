#!/usr/bin/env python3
"""Farsi golden-set eval for Pro session SAFETY FLAGS extraction (allergy/contraindication/consent).

Runs the real single-pass synthesis (``synthesize_session_report``) against the configured gateway and
asserts the ``safetyFlags`` output: when a capture STATES an allergy, a contraindication, or a consent
fact, the model must surface a flag of the right ``kind`` whose ``text`` is grounded in the report
language (native script, never translated). It must also NOT invent — a clean visit (or a plain
negation) yields no flags. Shares the harness in ``_common.py`` (tolerant Persian matching via
``contains``, ``knownGap`` xfail, the exit-code policy, the machine-readable scorecard):

* **Safety gates** — deterministic, over the flag kinds + grounded text. HARD pass/fail.

Run it where a gateway is reachable::

    docker exec engram-main-ai-engine-1 python /app/eval/safety_flags_eval.py

No gateway → the gateway cases SKIP; deterministic gate self-tests still run. Exit is SAFETY only.
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
    contains,
    env_models,
    exit_code,
    gateway_configured,
    write_scorecard,
)
from ai_engine.processing import synthesize_session_report  # noqa: E402

DOMAIN = {"label": "aesthetics clinic", "vocabulary": ["بوتاکس", "فیلر", "ژل", "واحد", "سی‌سی"]}


def _audio(capture_id: str, transcript: str) -> dict[str, Any]:
    return {"captureId": capture_id, "type": "audio", "transcript": transcript}


def _payload(captures: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "job": {"id": "eval-job", "jobType": "session_organize"},
        "session": {"reportTemplateKey": "default"},
        "reportTemplate": {"key": "default"},
        "aiModels": {},
        "sessionProcessingContext": {
            "domain": DOMAIN,
            "reportLanguage": "fa",
            "aftercareTemplates": [],
            "captures": {"audio": captures, "photos": [], "text": []},
            "referencePriorVisitTreatments": [],
        },
    }


# expect: list of flags the output MUST contain — each {kind, contains} where `contains` is a Farsi
# substring (or list of any-of substrings) the flag text must include (clinical content, never
# translated). expectNone=True asserts the GROUNDING guard: no flag must be emitted (don't invent).
CASES: list[dict[str, Any]] = [
    {
        "name": "allergy dictated → allergy flag, grounded in native script",
        "captures": [_audio("c1", "بیمار به لیدوکائین حساسیت داره. بیست واحد بوتاکس روی پیشونی زدم")],
        "expect": [{"kind": "allergy", "contains": "لیدوکائین"}],
    },
    {
        "name": "explicit penicillin allergy → allergy flag",
        "captures": [_audio("c1", "سابقهٔ آلرژی به پنی‌سیلین داره، حتماً تو پرونده ثبت بشه")],
        "expect": [{"kind": "allergy", "contains": "پنی‌سیلین"}],
    },
    {
        "name": "pregnancy contraindication → contraindication flag",
        "captures": [_audio("c1", "بیمار باردار هست، فعلاً بوتاکس انجام نمی‌دیم")],
        "expect": [{"kind": "contraindication", "contains": ["باردار", "بارداری"]}],
    },
    {
        "name": "anticoagulant contraindication → contraindication flag",
        "captures": [_audio("c1", "بیمار وارفارین مصرف می‌کنه، برای فیلر باید احتیاط کنیم")],
        "expect": [{"kind": "contraindication", "contains": "وارفارین"}],
    },
    {
        "name": "consent given → consent flag",
        "captures": [_audio("c1", "رضایت‌نامهٔ کتبی برای تزریق فیلر گرفته شد و امضا کرد")],
        "expect": [{"kind": "consent", "contains": "رضایت"}],
    },
    {
        "name": "allergy + consent in one visit → both flags",
        "captures": [
            _audio("c1", "به لیدوکائین حساسیت داره"),
            _audio("c2", "رضایت‌نامه برای بوتاکس گرفته شد"),
        ],
        "expect": [{"kind": "allergy", "contains": "لیدوکائین"}, {"kind": "consent", "contains": "رضایت"}],
    },
    {
        "name": "no safety content (plain treatment) → no flags invented",
        "captures": [_audio("c1", "یک سی‌سی فیلر توی گونه چپ تزریق شد")],
        "expect": [],
        "expectNone": True,
    },
    {
        "name": "negation of allergy is NOT a flag (no absence statements)",
        "captures": [_audio("c1", "هیچ آلرژی شناخته‌شده‌ای نداره. بیست واحد بوتاکس زدم")],
        "expect": [],
        "expectNone": True,
    },
]


def _contains_ok(needle: Any, text: str) -> bool:
    """Tolerant grounded-text match (ZWNJ/digit/letter-form folding via ``_common.contains``)."""
    options = needle if isinstance(needle, list) else [needle]
    return any(isinstance(option, str) and contains(text, option) for option in options)


def run_gates(output: dict[str, Any], case: dict[str, Any]) -> list[str]:
    """Apply the deterministic safety-flag gates to a synthesis output; return failures (empty == pass)."""
    flags = [f for f in (output.get("safetyFlags") or []) if isinstance(f, dict)]
    notes: list[str] = []

    if case.get("expectNone"):
        if flags:
            rendered = "; ".join(f"{f.get('kind')}:{f.get('text')}" for f in flags)
            notes.append(f"expected NO flags but got: {rendered}")
        return notes

    for wanted in case["expect"]:
        kind = wanted["kind"]
        matches = [f for f in flags if f.get("kind") == kind]
        if not matches:
            notes.append(f"{kind}: MISSING")
            continue
        if "contains" in wanted and not any(_contains_ok(wanted["contains"], str(f.get("text") or "")) for f in matches):
            got = " / ".join(str(f.get("text") or "") for f in matches)
            notes.append(f"{kind}: text not grounded (wanted ~{wanted['contains']!r}, got {got!r})")
    return notes


# --- Deterministic gate self-tests (synthetic OUTPUT dicts, no gateway) ---------------------------

def _output(flags: list[dict[str, Any]]) -> dict[str, Any]:
    return {"safetyFlags": flags}


GATE_SELF_TESTS: list[dict[str, Any]] = [
    {
        "name": "grounded allergy flag PASSES (tolerant match)",
        # ZWNJ vs space in «پنی‌سیلین» must still match — the whole point of the tolerant folding.
        "output": _output([{"kind": "allergy", "text": "حساسیت به پنی سیلین ثبت شد"}]),
        "case": {"expect": [{"kind": "allergy", "contains": "پنی‌سیلین"}]},
        "expectGatesPass": True,
    },
    {
        "name": "missing expected kind FAILS",
        "output": _output([]),
        "case": {"expect": [{"kind": "allergy", "contains": "لیدوکائین"}]},
        "expectGatesPass": False,
        "expectReasonContains": "MISSING",
    },
    {
        "name": "right kind but ungrounded text FAILS",
        "output": _output([{"kind": "allergy", "text": "حساسیت به وارفارین"}]),
        "case": {"expect": [{"kind": "allergy", "contains": "لیدوکائین"}]},
        "expectGatesPass": False,
        "expectReasonContains": "not grounded",
    },
    {
        "name": "any-of grounded text PASSES",
        "output": _output([{"kind": "contraindication", "text": "بیمار بارداری را اعلام کرد"}]),
        "case": {"expect": [{"kind": "contraindication", "contains": ["باردار", "بارداری"]}]},
        "expectGatesPass": True,
    },
    {
        "name": "expectNone with a flag present FAILS (invention)",
        "output": _output([{"kind": "allergy", "text": "حساسیت به لیدوکائین"}]),
        "case": {"expect": [], "expectNone": True},
        "expectGatesPass": False,
        "expectReasonContains": "expected NO flags",
    },
    {
        "name": "expectNone with no flags PASSES",
        "output": _output([]),
        "case": {"expect": [], "expectNone": True},
        "expectGatesPass": True,
    },
    {
        "name": "digit-folded consent text PASSES",
        "output": _output([{"kind": "consent", "text": "رضایت‌نامه ۲ صفحه‌ای امضا شد"}]),
        "case": {"expect": [{"kind": "consent", "contains": "رضایت"}]},
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
    """Run the synthetic Farsi safety cases on the gateway. Returns (pass, fail, known_gap, records)."""
    print("\n--- safety-flag cases (synthetic Farsi dictations → gateway) ---")
    safety_pass = safety_fail = known_gap = 0
    records: list[dict[str, Any]] = []
    for index, case in enumerate(CASES, start=1):
        try:
            output = synthesize_session_report(_payload(case["captures"]))
        except Exception as exc:  # noqa: BLE001 — gateway/network: report and stop scoring.
            print(f"  [{index}] ERROR {case['name']}: synthesis failed: {exc!r}")
            print("  SKIP: gateway unreachable — remaining cases not scored.")
            break
        if output is None:
            print(f"  [{index}] SAFETY FAIL {case['name']}: synthesis returned no usable output")
            safety_fail += 1
            records.append({"id": case["name"], "safety": "fail", "judge": {}, "reasons": ["no usable output"]})
            continue
        problems = run_gates(output, case)
        flags = output.get("safetyFlags") or []
        summary = "; ".join(f"{f.get('kind')}={f.get('text')}" for f in flags) or "(none)"
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
        print("\nSKIP: no AI gateway configured. Safety-flag cases not run; deterministic self-tests above stand.")
        write_scorecard(
            "safety_flags_eval",
            metrics={"self_tests_ok": int(self_tests_ok), "safety_pass": 0, "safety_fail": 0, "known_gap": 0, "cases_total": 0},
            models_under_test=env_models("AI_ENGINE_REPORT_SYNTHESIS_MODEL", "AI_ENGINE_TRANSCRIPTION_MODEL"),
        )
        return 0 if self_tests_ok else 1

    safety_pass, safety_fail, known_gap, records = run_cases()

    print(f"\n{'=' * 8} SAFETY-FLAGS SCORECARD {'=' * 8}")
    print(f"  self-tests:    {'PASS' if self_tests_ok else 'FAIL (harness bug)'}")
    print(f"  safety gates:  {safety_pass} pass / {safety_fail} fail / {known_gap} known-gap")
    write_scorecard(
        "safety_flags_eval",
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
