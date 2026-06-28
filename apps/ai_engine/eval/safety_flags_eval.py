#!/usr/bin/env python3
"""Farsi golden-set eval for Pro session SAFETY FLAGS extraction (allergy/contraindication/consent).

Opt-in eval that runs the real single-pass synthesis (``synthesize_session_report``) against the
configured gateway and asserts the ``safetyFlags`` output: when a capture STATES an allergy, a
contraindication, or a consent fact, the model must surface a flag of the right ``kind`` whose
``text`` is grounded in the report language (native script, never translated). It must also NOT
invent — a clean visit (or a plain negation) yields no flags. This guards the opt-out safety
behaviour: safety errs toward inclusion, but only for things a capture actually says.

Run it where a gateway is reachable::

    docker exec engram-main-ai-engine-1 python /app/eval/safety_flags_eval.py

No gateway → SKIP (exit 0). With a gateway it exits non-zero if any case fails.
"""
from __future__ import annotations

import sys
from typing import Any

sys.path.insert(0, ".")
sys.path.insert(0, "/app")

from ai_engine.processing import synthesize_session_report, transcription_is_configured  # noqa: E402

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
    if isinstance(needle, list):
        return any(isinstance(option, str) and option in text for option in needle)
    return isinstance(needle, str) and needle in text


def _check(case: dict[str, Any], output: dict[str, Any]) -> tuple[bool, list[str]]:
    flags = [f for f in (output.get("safetyFlags") or []) if isinstance(f, dict)]
    notes: list[str] = []

    if case.get("expectNone"):
        if flags:
            rendered = "; ".join(f"{f.get('kind')}:{f.get('text')}" for f in flags)
            notes.append(f"expected NO flags but got: {rendered}")
        return (not notes), notes

    for wanted in case["expect"]:
        kind = wanted["kind"]
        matches = [f for f in flags if f.get("kind") == kind]
        if not matches:
            notes.append(f"{kind}: MISSING")
            continue
        if "contains" in wanted and not any(_contains_ok(wanted["contains"], str(f.get("text") or "")) for f in matches):
            got = " / ".join(str(f.get("text") or "") for f in matches)
            notes.append(f"{kind}: text not grounded (wanted ~{wanted['contains']!r}, got {got!r})")
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
        flags = output.get("safetyFlags") or []
        summary = "; ".join(f"{f.get('kind')}={f.get('text')}" for f in flags) or "(none)"
        if ok:
            print(f"[{index}] PASS  {case['name']}  → {summary}")
            passed += 1
        else:
            print(f"[{index}] FAIL  {case['name']}  → {summary}  | {', '.join(notes)}")
            failed += 1
    total = passed + failed
    print(f"\nSafety flags eval: {passed}/{total} passed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
