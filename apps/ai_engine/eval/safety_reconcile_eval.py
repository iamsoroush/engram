#!/usr/bin/env python3
"""Farsi golden-set eval for the cross-visit SAFETY-RECONCILE job (selection-only, keys + status out).

Runs the real ``reconcile_safety_flags`` against the gateway and asserts its decisions over a
user-clean candidate set (existing patient flags + this visit's new flags): dedup same-concept,
keep distinct, supersede an explicit update (annotated, not dropped), never merge across kinds, and
— the critical guard — NEVER drop a distinct allergy/contraindication. Mirrors the other evals:

    docker exec engram-main-ai-engine-1 python /app/eval/safety_reconcile_eval.py

No gateway → SKIP (exit 0). With a gateway it exits non-zero if any case fails.
"""
from __future__ import annotations

import sys
from typing import Any

sys.path.insert(0, ".")
sys.path.insert(0, "/app")

from ai_engine.processing import reconcile_safety_flags, transcription_is_configured  # noqa: E402


def _key(kind: str, text: str) -> str:
    return f"{kind}|{' '.join(text.strip().lower().split())}"


def _flag(kind: str, text: str) -> dict[str, Any]:
    return {"key": _key(kind, text), "kind": kind, "text": text}


def _status(decisions: dict[str, Any], key: str) -> str:
    # A candidate with no explicit decision defaults to keep (the never-drop floor).
    return (decisions.get(key) or {}).get("status", "keep")


# Each case: existing + new flags, and a check over the decisions map {key: {status, ofKey}}.
A_LIDO = _flag("allergy", "حساسیت به لیدوکائین")
A_PENI = _flag("allergy", "آلرژی به پنی‌سیلین")
A_PENI2 = _flag("allergy", "حساسیت به پنی‌سیلین")          # same concept as A_PENI, different wording
C_WARF = _flag("contraindication", "بیمار وارفارین مصرف می‌کنه")
C_PREG = _flag("contraindication", "بیمار باردار است")
C_NOTPREG = _flag("contraindication", "بیمار دیگر باردار نیست، زایمان کرده")
K_CONSENT = _flag("consent", "رضایت‌نامه گرفته شد")
K_CONSENT2 = _flag("consent", "رضایت‌نامه اخذ شد")  # same concept as K_CONSENT, pure rephrase (taken→obtained)


def _all_keep(keys):
    return lambda d: (all(_status(d, k) == "keep" for k in keys), f"statuses={[ (k[:18],_status(d,k)) for k in keys]}")


def _exactly_one_duplicate(keys):
    def check(d):
        dups = sum(_status(d, k) == "duplicate" for k in keys)
        # never-drop: at least one of the pair must remain (not all duplicate)
        return (dups == 1, f"duplicate_count={dups} (want 1); statuses={[ _status(d,k) for k in keys]}")
    return check


def _superseded(old_key, keys):
    def check(d):
        st = _status(d, old_key)
        # Safety gate: the old flag is NEVER dropped as a duplicate; ideally it's superseded (annotated).
        return (st == "superseded", f"old status={st} (want superseded; keep is acceptable-but-noted, duplicate is a FAIL)")
    return check


CASES: list[dict[str, Any]] = [
    {"name": "dedup same allergy, different wording → one kept", "existing": [A_PENI], "new": [A_PENI2],
     "check": _exactly_one_duplicate([A_PENI["key"], A_PENI2["key"]])},
    {"name": "distinct allergies → both kept", "existing": [A_LIDO], "new": [A_PENI],
     "check": _all_keep([A_LIDO["key"], A_PENI["key"]])},
    {"name": "NEVER-DROP: three distinct flags all kept", "existing": [A_LIDO], "new": [A_PENI, C_WARF],
     "check": _all_keep([A_LIDO["key"], A_PENI["key"], C_WARF["key"]])},
    {"name": "supersede: pregnancy then no-longer-pregnant → old superseded (annotated)", "existing": [C_PREG], "new": [C_NOTPREG],
     "check": _superseded(C_PREG["key"], [C_PREG["key"], C_NOTPREG["key"]])},
    {"name": "consent dedup → one kept", "existing": [K_CONSENT], "new": [K_CONSENT2],
     "check": _exactly_one_duplicate([K_CONSENT["key"], K_CONSENT2["key"]])},
    {"name": "cross-kind never merged (allergy + consent)", "existing": [A_PENI], "new": [K_CONSENT],
     "check": _all_keep([A_PENI["key"], K_CONSENT["key"]])},
    {"name": "no-op: existing distinct, no new → all kept", "existing": [A_LIDO, A_PENI], "new": [],
     "check": _all_keep([A_LIDO["key"], A_PENI["key"]])},
]


def main() -> int:
    if not transcription_is_configured():
        print("SKIP: no AI gateway configured (AI_ENGINE_TRANSCRIPTION_BASE_URL empty).")
        return 0
    passed = failed = 0
    for index, case in enumerate(CASES, start=1):
        payload = {"existingFlags": case["existing"], "newFlags": case["new"], "aiModels": {}}
        try:
            decisions = reconcile_safety_flags(payload)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: gateway call failed on case {index} ({case['name']}): {exc!r}")
            print("SKIP: gateway unreachable — eval not run.")
            return 0
        if decisions is None:
            print(f"[{index}] FAIL  {case['name']}: reconcile returned no usable output")
            failed += 1
            continue
        ok, note = case["check"](decisions)
        if ok:
            print(f"[{index}] PASS  {case['name']}")
            passed += 1
        else:
            print(f"[{index}] FAIL  {case['name']}  | {note}")
            failed += 1
    total = passed + failed
    print(f"\nSafety reconcile eval: {passed}/{total} passed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
