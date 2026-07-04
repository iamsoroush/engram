#!/usr/bin/env python3
"""Farsi golden-set eval for Pro AFTERCARE selection + dictation-vs-protocol conflict detection.

Runs the real single-pass synthesis (``synthesize_session_report``) against the configured gateway and
asserts the ``aftercareSelections`` output: for the procedures performed this visit, the model must
(a) pick the right clinic protocol(s) by clinical relevance — COMPLETENESS, one per performed
procedure — and (b) when the clinician DICTATES aftercare that differs from a protocol, flag THAT
protocol (per-procedure, same-topic) as conflicts/superseded, never a different one. Shares the harness
in ``_common.py`` (``knownGap`` xfail, the exit-code policy, the machine-readable scorecard):

* **Safety gates** — deterministic, over the selection statuses. HARD pass/fail.

Run it where a gateway is reachable::

    docker exec engram-main-ai-engine-1 python /app/eval/aftercare_conflict_eval.py

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
    capture_prompt_version,
    env_models,
    exit_code,
    gateway_configured,
    write_scorecard,
)
from ai_engine.processing import synthesize_session_report  # noqa: E402

DOMAIN = {"label": "aesthetics clinic", "vocabulary": ["بوتاکس", "فیلر", "ژل", "واحد", "سی‌سی"]}

# The clinic's protocols (mirror the demo clinic). botox → sun/sauna 3 DAYS; filler → high-heat 2 WEEKS.
TEMPLATES = [
    {
        "id": "tmpl-botox",
        "name": "مراقبت بعد از بوتاکس",
        "procedureType": "botox",
        "body": "تا ۴ ساعت دراز نکشید. ۲۴ ساعت ورزش سنگین و ماساژ ناحیه ممنوع. تا ۳ روز از سونا و آفتاب مستقیم پرهیز کنید.",
    },
    {
        "id": "tmpl-filler",
        "name": "مراقبت بعد از فیلر",
        "procedureType": "filler",
        "body": "تا ۲۴ ساعت آرایش نکنید. کمپرس سرد برای کاهش تورم. تا ۲ هفته از حرارت زیاد (سونا/سولاریوم) پرهیز کنید.",
    },
    {
        "id": "tmpl-laser",
        "name": "مراقبت بعد از لیزر",
        "procedureType": "laser",
        "body": "تا ۴۸ ساعت ناحیه را خنک نگه دارید و دست نزنید. تا ۲ هفته حتماً ضدآفتاب استفاده کنید و از آفتاب مستقیم پرهیز کنید. از لایه‌برداری و سونا خودداری کنید.",
    },
]


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
            "aftercareTemplates": TEMPLATES,
            "captures": {"audio": captures, "photos": [], "text": []},
            "referencePriorVisitTreatments": [],
        },
    }


# expect: {templateId: status}. "applies" must be exact; "flag" accepts conflicts OR superseded.
CASES: list[dict[str, Any]] = [
    {
        "name": "botox only, no aftercare dictated → applies",
        "captures": [_audio("c1", "بیست واحد بوتاکس روی پیشونی تزریق شد")],
        "expect": {"tmpl-botox": "applies"},
    },
    {
        "name": "botox SUN conflict (clinician 1 week vs protocol 3 days) → botox flagged",
        "captures": [_audio("c1", "بیست واحد بوتاکس روی پیشونی. به بیمار گفتم تا یک هفته از آفتاب مستقیم پرهیز کنه")],
        "expect": {"tmpl-botox": "flag"},
    },
    {
        "name": "botox+filler, botox sun conflict, filler unaffected → botox flag, filler applies",
        "captures": [_audio("c1", "بیست واحد بوتاکس پیشونی و یک سی‌سی فیلر لب. گفتم تا یک هفته از آفتاب مستقیم دوری کنه")],
        "expect": {"tmpl-botox": "flag", "tmpl-filler": "applies"},
    },
    {
        "name": "filler HEAT conflict (clinician 3 days vs protocol 2 weeks) → filler flagged",
        "captures": [_audio("c1", "یک سی‌سی فیلر توی لب. به بیمار گفتم فقط سه روز از حرارت و سونا پرهیز کنه")],
        "expect": {"tmpl-filler": "flag"},
    },
    {
        "name": "botox+filler, no aftercare dictated → both apply",
        "captures": [_audio("c1", "بیست واحد بوتاکس پیشونی و یک سی‌سی فیلر لب تزریق شد")],
        "expect": {"tmpl-botox": "applies", "tmpl-filler": "applies"},
    },
    {
        "name": "botox, clinician gave own full aftercare → superseded/conflicts",
        "captures": [_audio("c1", "بوتاکس پیشونی. مراقبت بعد از درمان رو کامل خودم توضیح دادم: فقط کمپرس یخ و استراحت، محدودیت آفتاب نداره")],
        "expect": {"tmpl-botox": "flag"},
    },
    {
        "name": "botox, clinician RESTATES the protocol's own 3-day sun rule → applies (not flagged)",
        "captures": [_audio("c1", "بوتاکس پیشونی. مثل همیشه گفتم تا سه روز از آفتاب و سونا پرهیز کنه")],
        "expect": {"tmpl-botox": "applies"},
    },
    {
        "name": "botox+filler performed, laser NOT performed → laser must not be selected",
        "captures": [_audio("c1", "بیست واحد بوتاکس پیشونی و یک سی‌سی فیلر لب تزریق شد، بدون لیزر")],
        "expect": {"tmpl-botox": "applies", "tmpl-filler": "applies"},
    },
    {
        "name": "botox+filler, sun conflict attributed to botox, unrelated remark ignored → botox flag, filler applies",
        "captures": [_audio("c1", "بیست واحد بوتاکس پیشونی و یک سی‌سی فیلر لب. گفتم تا یک هفته از آفتاب پرهیز کنه. ضمناً پوستش خیلی خوب بود و ناحیه رو کمی ماساژ دادم")],
        "expect": {"tmpl-botox": "flag", "tmpl-filler": "applies"},
    },
]


def _status_ok(expected: str, actual: str | None) -> bool:
    if expected == "applies":
        return actual == "applies"
    return actual in ("conflicts", "superseded")  # "flag": the clinician's words differ — either is fine


def run_gates(output: dict[str, Any], expect: dict[str, str]) -> list[str]:
    """Apply the deterministic aftercare-selection gates; return failures (empty == pass)."""
    selections = [s for s in (output.get("aftercareSelections") or []) if isinstance(s, dict)]
    by_id = {s.get("templateId"): s.get("status") for s in selections}
    notes: list[str] = []
    for template_id, expected_status in expect.items():
        actual = by_id.get(template_id)
        if actual is None:
            notes.append(f"{template_id}: MISSING (expected {expected_status})")
        elif not _status_ok(expected_status, actual):
            notes.append(f"{template_id}: {actual}≠{expected_status}")
    for template_id, status in by_id.items():
        if template_id not in expect:
            notes.append(f"{template_id}: UNEXPECTED ({status}) — that procedure wasn't performed")
    return notes


# --- Deterministic gate self-tests (synthetic OUTPUT dicts, no gateway) ---------------------------

def _output(selections: list[dict[str, Any]]) -> dict[str, Any]:
    return {"aftercareSelections": selections}


GATE_SELF_TESTS: list[dict[str, Any]] = [
    {
        "name": "applies as expected PASSES",
        "output": _output([{"templateId": "tmpl-botox", "status": "applies"}]),
        "expect": {"tmpl-botox": "applies"},
        "expectGatesPass": True,
    },
    {
        "name": "flag accepts conflicts",
        "output": _output([{"templateId": "tmpl-botox", "status": "conflicts"}]),
        "expect": {"tmpl-botox": "flag"},
        "expectGatesPass": True,
    },
    {
        "name": "flag accepts superseded",
        "output": _output([{"templateId": "tmpl-filler", "status": "superseded"}]),
        "expect": {"tmpl-filler": "flag"},
        "expectGatesPass": True,
    },
    {
        "name": "applies-expected but conflicts FAILS",
        "output": _output([{"templateId": "tmpl-botox", "status": "conflicts"}]),
        "expect": {"tmpl-botox": "applies"},
        "expectGatesPass": False,
        "expectReasonContains": "≠applies",
    },
    {
        "name": "flag-expected but applies FAILS",
        "output": _output([{"templateId": "tmpl-filler", "status": "applies"}]),
        "expect": {"tmpl-filler": "flag"},
        "expectGatesPass": False,
        "expectReasonContains": "≠flag",
    },
    {
        "name": "missing expected selection FAILS",
        "output": _output([]),
        "expect": {"tmpl-botox": "applies"},
        "expectGatesPass": False,
        "expectReasonContains": "MISSING",
    },
    {
        "name": "selecting a not-performed protocol FAILS (over-selection)",
        "output": _output([{"templateId": "tmpl-botox", "status": "applies"}, {"templateId": "tmpl-filler", "status": "applies"}]),
        "expect": {"tmpl-botox": "applies"},
        "expectGatesPass": False,
        "expectReasonContains": "UNEXPECTED",
    },
]


# --- Runners --------------------------------------------------------------------------------------


def run_gate_self_tests() -> bool:
    print("--- safety-gate self-tests (deterministic, no gateway) ---")
    ok = True
    for index, case in enumerate(GATE_SELF_TESTS, start=1):
        problems = run_gates(case["output"], case["expect"])
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
    """Run the synthetic aftercare cases on the gateway.

    Returns ``(pass, fail, known_gap, records, prompt_version)`` — ``prompt_version`` is the first
    usable output's prompt-version stamp (``None`` until the job emits one; see ``capture_prompt_version``).
    """
    print("\n--- aftercare-conflict cases (synthetic Farsi dictations → gateway) ---")
    safety_pass = safety_fail = known_gap = 0
    records: list[dict[str, Any]] = []
    prompt_version: str | None = None
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
        prompt_version = prompt_version or capture_prompt_version(output)
        problems = run_gates(output, case["expect"])
        selections = output.get("aftercareSelections") or []
        summary = "; ".join(f"{s.get('templateId')}={s.get('status')}" for s in selections) or "(none)"
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


def main() -> int:
    self_tests_ok = run_gate_self_tests()
    if not gateway_configured():
        print("\nSKIP: no AI gateway configured. Aftercare cases not run; deterministic self-tests above stand.")
        write_scorecard(
            "aftercare_conflict_eval",
            metrics={"self_tests_ok": int(self_tests_ok), "safety_pass": 0, "safety_fail": 0, "known_gap": 0, "cases_total": 0},
            models_under_test=env_models("AI_ENGINE_REPORT_SYNTHESIS_MODEL", "AI_ENGINE_TRANSCRIPTION_MODEL"),
        )
        return 0 if self_tests_ok else 1

    safety_pass, safety_fail, known_gap, records, prompt_version = run_cases()

    print(f"\n{'=' * 8} AFTERCARE-CONFLICT SCORECARD {'=' * 8}")
    print(f"  self-tests:    {'PASS' if self_tests_ok else 'FAIL (harness bug)'}")
    print(f"  safety gates:  {safety_pass} pass / {safety_fail} fail / {known_gap} known-gap")
    write_scorecard(
        "aftercare_conflict_eval",
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
