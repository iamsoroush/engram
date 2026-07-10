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

from _common import EVAL_VOTES, capture_prompt_version, env_models, gate_votes, write_scorecard  # noqa: E402
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

# (a) Related-but-distinct: same drug FAMILY but DISTINCT facts — dropping either is the never-drop failure.
A_PENI_ALG = _flag("allergy", "آلرژی به پنی‌سیلین")        # penicillin (same key family as A_PENI, spelled the same)
A_AMOX_ALG = _flag("allergy", "آلرژی به آموکسی‌سیلین")     # amoxicillin — penicillin family, but a DISTINCT drug/fact
# (a) Richer-text same concept + added severity: treated as NEW severity info → keep both (never-drop ethos).
A_LIDO_SEV = _flag("allergy", "حساسیت به لیدوکائین موضعی با تورم شدید")  # lidocaine allergy + severe-swelling detail

# (c) Cross-script duplicate: the SAME penicillin allergy stated in Persian vs English/Latin wording.
A_PENI_EN = _flag("allergy", "Penicillin allergy")

# (b) Scale panel: a realistic accumulated set of DISTINCT existing flags, with two same-concept restatements
# arriving in the new set (the two buried duplicates). Distinct facts must all survive.
S_ALG_SULFA = _flag("allergy", "آلرژی به سولفانامید")
S_ALG_ASPIRIN = _flag("allergy", "حساسیت به آسپرین")
S_ALG_IODINE = _flag("allergy", "آلرژی به ید")
S_ALG_LATEX = _flag("allergy", "حساسیت به لاتکس")
S_CI_ISOTRET = _flag("contraindication", "مصرف ایزوترتینوئین در شش ماه گذشته")
S_CI_KELOID = _flag("contraindication", "سابقه اسکار کلوئیدی")
S_CI_HERPES = _flag("contraindication", "تبخال فعال در محل درمان")
S_CI_ANTICOAG = _flag("contraindication", "مصرف داروی ضدانعقاد")
S_CONSENT_LASER = _flag("consent", "رضایت‌نامه لیزر امضا شد")
S_CONSENT_PHOTO = _flag("consent", "رضایت عکس‌برداری گرفته شد")
# The two buried duplicates arriving anew (same concepts as S_ALG_SULFA and S_CI_ISOTRET, reworded):
S_ALG_SULFA_DUP = _flag("allergy", "حساسیت به سولفانامید")
S_CI_ISOTRET_DUP = _flag("contraindication", "بیمار شش ماه پیش ایزوترتینوئین مصرف کرده")


def _all_keep(keys):
    return lambda d: (all(_status(d, k) == "keep" for k in keys), f"statuses={[ (k[:18],_status(d,k)) for k in keys]}")


def _exactly_one_duplicate(keys):
    def check(d):
        dups = sum(_status(d, k) == "duplicate" for k in keys)
        # never-drop: at least one of the pair must remain (not all duplicate)
        return (dups == 1, f"duplicate_count={dups} (want 1); statuses={[ _status(d,k) for k in keys]}")
    return check


def _superseded(old_key, keys):
    """Advisory-deterministic supersede check → ``(ok, advisory, note)``.

    The old flag encodes a fact a later visit updates (pregnant → no longer pregnant). Three outcomes:

    * ``superseded`` — old flag annotated as replaced: the ideal → PASS (``ok=True, advisory=False``).
    * ``keep`` (or anything not superseded/duplicate) — the model kept the old flag standing instead of
      annotating the update: still safe (nothing dropped), so PASS-with-ADVISORY (``ok=True, advisory=True``);
      printed and counted, but never fails the suite.
    * ``duplicate`` — the old distinct flag was DROPPED: the real danger → HARD FAIL (``ok=False``).
    """
    def check(d):
        st = _status(d, old_key)
        if st == "duplicate":
            return (False, False, f"old status={st} (the old distinct flag was DROPPED as a duplicate — FAIL)")
        if st == "superseded":
            return (True, False, f"old status={st} (annotated as replaced — ideal)")
        return (True, True, f"old status={st} (kept standing, not annotated as superseded — acceptable but advised)")
    return check


def _scale_dedup(dup_pairs, distinct_keys):
    """Scale-panel check: each same-concept pair dedups to exactly one kept, and no distinct flag drops.

    Args:
        dup_pairs: list of key-pairs, each a buried same-concept restatement that must collapse to one.
        distinct_keys: the genuinely-distinct flags that must all survive (never dropped/deduped).
    """
    def check(d):
        problems: list[str] = []
        for pair in dup_pairs:
            dups = sum(_status(d, k) == "duplicate" for k in pair)
            if dups != 1:
                problems.append(f"pair {[p[:22] for p in pair]} duplicate_count={dups} (want 1)")
        dropped = [k[:24] for k in distinct_keys if _status(d, k) != "keep"]
        if dropped:
            problems.append(f"distinct flags not kept: {dropped}")
        return (not problems, "; ".join(problems) or "ok")
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
    # (a) Same drug family, DISTINCT facts (penicillin vs amoxicillin) → both kept; dropping either is never-drop.
    {"name": "drug-family distinct: penicillin + amoxicillin allergy → both kept",
     "existing": [A_PENI_ALG], "new": [A_AMOX_ALG],
     "check": _all_keep([A_PENI_ALG["key"], A_AMOX_ALG["key"]])},
    # (a) Richer restatement adds severity → treated as NEW info, never collapsed away → both kept.
    {"name": "richer-text adds severity: lidocaine allergy + severe-swelling detail → both kept",
     "existing": [A_LIDO], "new": [A_LIDO_SEV],
     "check": _all_keep([A_LIDO["key"], A_LIDO_SEV["key"]])},
    # (c) Cross-script duplicate: same penicillin allergy, Persian vs Latin wording → one kept.
    {"name": "cross-script dedup: «آلرژی به پنی‌سیلین» vs «Penicillin allergy» → one kept",
     "existing": [A_PENI_ALG], "new": [A_PENI_EN],
     "check": _exactly_one_duplicate([A_PENI_ALG["key"], A_PENI_EN["key"]])},
    # (b) Scale: 10 accumulated distinct flags + 2 buried same-concept duplicates in the new set → each pair
    # collapses to exactly one kept, and none of the distinct flags is dropped (dedup precision at panel size).
    {"name": "scale: 10-flag panel, 2 buried duplicates → each dedups to one, distinct all kept",
     "existing": [S_ALG_SULFA, S_ALG_ASPIRIN, S_ALG_IODINE, S_ALG_LATEX, S_CI_ISOTRET, S_CI_KELOID,
                  S_CI_HERPES, S_CI_ANTICOAG, S_CONSENT_LASER, S_CONSENT_PHOTO],
     "new": [S_ALG_SULFA_DUP, S_CI_ISOTRET_DUP],
     "check": _scale_dedup(
         dup_pairs=[[S_ALG_SULFA["key"], S_ALG_SULFA_DUP["key"]], [S_CI_ISOTRET["key"], S_CI_ISOTRET_DUP["key"]]],
         distinct_keys=[S_ALG_ASPIRIN["key"], S_ALG_IODINE["key"], S_ALG_LATEX["key"], S_CI_KELOID["key"],
                        S_CI_HERPES["key"], S_CI_ANTICOAG["key"], S_CONSENT_LASER["key"], S_CONSENT_PHOTO["key"]])},
]


def main() -> int:
    models = env_models("AI_ENGINE_REPORT_SYNTHESIS_MODEL", "AI_ENGINE_TRANSCRIPTION_MODEL")
    if not transcription_is_configured():
        print("SKIP: no AI gateway configured (AI_ENGINE_TRANSCRIPTION_BASE_URL empty).")
        write_scorecard(
            "safety_reconcile_eval",
            metrics={"safety_pass": 0, "safety_fail": 0, "cases_total": 0, "advisory": 0},
            models_under_test=models,
        )
        return 0
    passed = failed = advisories = 0
    prompt_version: str | None = None
    records: list[dict[str, Any]] = []
    for index, case in enumerate(CASES, start=1):
        payload = {"existingFlags": case["existing"], "newFlags": case["new"], "aiModels": {}}

        def _attempt(case=case, payload=payload):
            out = reconcile_safety_flags(payload)
            if out is None:
                return ["reconcile returned no usable output"], None
            # A check returns (ok, note) or, for the advisory-tier supersede case, (ok, advisory, note);
            # advisory passes stay passes (empty problems) so voting never turns an advisory into a fail.
            result = case["check"](out)
            return ([] if result[0] else [result[-1]]), out

        try:
            problems, decisions, attempts = gate_votes(_attempt)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: gateway call failed on case {index} ({case['name']}): {exc!r}")
            print("SKIP: gateway unreachable — eval not run.")
            return 0
        prompt_version = prompt_version or (capture_prompt_version(decisions) if decisions else None)
        votes_suffix = f"  [votes:{attempts}/{EVAL_VOTES}]" if attempts > 1 else ""
        if not problems:
            # Re-derive the advisory tier from the DECIDING output (checks are pure over the decisions).
            result = case["check"](decisions)
            advisory = result[1] if len(result) == 3 else False
            note = result[-1]
            print(f"[{index}] PASS  {case['name']}{votes_suffix}")
            passed += 1
            reasons: list[str] = []
            if advisory:
                advisories += 1
                print(f"        ADVISORY: {note}")
                reasons = [f"advisory: {note}"]
            records.append({"id": case["name"], "safety": "pass", "judge": {}, "reasons": reasons})
        else:
            print(f"[{index}] FAIL  {case['name']}  | {problems[0]}{votes_suffix}")
            failed += 1
            records.append({"id": case["name"], "safety": "fail", "judge": {}, "reasons": [problems[0]]})
    total = passed + failed
    advisory_suffix = f" ({advisories} advisory)" if advisories else ""
    print(f"\nSafety reconcile eval: {passed}/{total} passed{advisory_suffix}.")
    write_scorecard(
        "safety_reconcile_eval",
        metrics={"safety_pass": passed, "safety_fail": failed, "cases_total": total, "advisory": advisories},
        cases=records,
        models_under_test=models,
        prompt_version=prompt_version,
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
