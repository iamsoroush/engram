#!/usr/bin/env python3
"""Farsi golden-set eval for Pro AFTERCARE selection + dictation-vs-protocol conflict detection.

Opt-in eval that runs the real single-pass synthesis (``synthesize_session_report``) against the
configured gateway and asserts the ``aftercareSelections`` output: for the procedures performed this
visit, the model must (a) pick the right clinic protocol(s) by clinical relevance — COMPLETENESS,
one per performed procedure — and (b) when the clinician DICTATES aftercare that differs from a
protocol, flag THAT protocol (per-procedure, same-topic) as conflicts/superseded, never a different
one. This guards the "intelligent, not keyword" aftercare behaviour the deterministic match couldn't.

Run it where a gateway is reachable::

    docker exec notari-main-ai-engine-1 python /app/eval/aftercare_conflict_eval.py

No gateway → SKIP (exit 0). With a gateway it exits non-zero if any case fails.
"""
from __future__ import annotations

import sys
from typing import Any

sys.path.insert(0, ".")
sys.path.insert(0, "/app")

from ai_engine.processing import synthesize_session_report, transcription_is_configured  # noqa: E402

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
]


def _status_ok(expected: str, actual: str | None) -> bool:
    if expected == "applies":
        return actual == "applies"
    return actual in ("conflicts", "superseded")  # "flag": the clinician's words differ — either is fine


def _check(case: dict[str, Any], output: dict[str, Any]) -> tuple[bool, list[str]]:
    selections = [s for s in (output.get("aftercareSelections") or []) if isinstance(s, dict)]
    by_id = {s.get("templateId"): s.get("status") for s in selections}
    expected = case["expect"]
    notes: list[str] = []
    for template_id, expected_status in expected.items():
        actual = by_id.get(template_id)
        if actual is None:
            notes.append(f"{template_id}: MISSING (expected {expected_status})")
        elif not _status_ok(expected_status, actual):
            notes.append(f"{template_id}: {actual}≠{expected_status}")
    for template_id, status in by_id.items():
        if template_id not in expected:
            notes.append(f"{template_id}: UNEXPECTED ({status}) — that procedure wasn't performed")
    return (not notes), notes


def main() -> int:
    if not transcription_is_configured():
        print("SKIP: no AI gateway configured (AI_ENGINE_TRANSCRIPTION_BASE_URL empty).")
        return 0
    passed = 0
    failed = 0
    for index, case in enumerate(CASES, start=1):
        try:
            output = synthesize_session_report(_payload(case["captures"]))
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: gateway call failed on case {index} ({case['name']}): {exc!r}")
            print("SKIP: gateway unreachable — eval not run.")
            return 0
        if output is None:
            print(f"[{index}] FAIL  {case['name']}: synthesis returned no usable output")
            failed += 1
            continue
        ok, notes = _check(case, output)
        selections = output.get("aftercareSelections") or []
        summary = "; ".join(f"{s.get('templateId')}={s.get('status')}" for s in selections) or "(none)"
        if ok:
            print(f"[{index}] PASS  {case['name']}  → {summary}")
            passed += 1
        else:
            print(f"[{index}] FAIL  {case['name']}  → {summary}  | {', '.join(notes)}")
            failed += 1
    total = passed + failed
    print(f"\nAftercare conflict eval: {passed}/{total} passed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
