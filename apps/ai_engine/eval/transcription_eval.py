#!/usr/bin/env python3
"""Golden-set eval for AUDIO TRANSCRIPTION — the foundation job (garbage in → garbage everywhere).

Transcription is the highest-stakes AI job: a mis-heard dose token (۲ vs ۳ vs ۲۳), a romanized Persian
name, or a dropped brand/lot poisons everything downstream (treatments, matching, the patient share).
This eval scores the real gateway on two tiers (shared harness in ``_common.py``):

* **Safety gates** — deterministic matchers (substring / numeric-token / presence / no-Latin). HARD
  pass/fail; the dose-token / no-romanization gate.
* **Quality (LLM judge)** — native-script / dose / brand-lot fidelity, completeness, no-hallucination,
  scored 0..1. Advisory by default (``EVAL_STRICT_QUALITY=1`` to gate on it too).

Transcription can only be truly evaluated on REAL AUDIO, so it is fixture-driven: drop a clip at the
fixtures dir (``EVAL_FIXTURES_DIR`` or in-repo ``eval/fixtures/transcription/``) as ``<case>.m4a`` plus
a sibling ``<case>.json`` (format: ``docs/ai_engine/evals.md`` "Expectations format") and it is scored. Until
recordings land, deterministic **gate self-tests** + gateway **judge smoke cases** keep it honest.

Run::

    docker exec notari-main-ai-engine-1 python /app/eval/transcription_eval.py

No gateway → the gateway tier SKIPS; self-tests still run. Exit code is SAFETY only unless EVAL_STRICT_QUALITY=1.
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
    AUDIO_SUFFIXES,
    DEFAULT_MIN_SCORE,
    STRICT_QUALITY,
    capture_prompt_version,
    contains,
    env_models,
    exit_code,
    gateway_configured,
    judge,
    latin_offenders,
    load_fixtures,
    min_score,
    number_tokens,
    quality_line,
    write_scorecard,
)
from ai_engine.processing import transcribe_audio_content  # noqa: E402

# Realistic aesthetics-clinic framing so the gateway prompt matches production (vertical-agnostic by
# contract — supplied as data). A fixture's "context" is merged over this.
TRANSCRIPTION_CONTEXT: dict[str, Any] = {
    "preferredLanguage": "auto",
    "domain": {
        "label": "aesthetics clinic",
        "vocabulary": ["بوتاکس", "فیلر", "ژل", "واحد", "سی‌سی", "ژوویدرم", "رستیلین", "کانولا"],
    },
}
JUDGE_DIMENSIONS = ("nativeScript", "doseFidelity", "brandLotFidelity", "completeness", "noHallucination")


# --- Safety gates (deterministic) -----------------------------------------------------------------


def run_gates(transcript: str, language: str | None, expect: dict[str, Any]) -> list[str]:
    """Apply the deterministic safety gates; return failure reasons (empty list == all gates pass)."""
    problems: list[str] = []

    for token in expect.get("containsFa", []):
        if not contains(transcript, token):
            problems.append(f"missing required {token!r}")

    for group in expect.get("containsAny", []):
        options = group if isinstance(group, list) else [group]
        if not any(contains(transcript, option) for option in options):
            problems.append(f"none of {options} present")

    if expect.get("numbers"):
        present = number_tokens(transcript)
        for number in expect["numbers"]:
            token = str(number).rstrip("0").rstrip(".") if isinstance(number, float) else str(number)
            if str(number) not in present and token not in present:
                problems.append(f"number {number} not transcribed as a digit token (have {sorted(present) or '∅'})")

    if expect.get("numbersForbidden"):
        present = number_tokens(transcript)
        for number in expect["numbersForbidden"]:
            token = str(number).rstrip("0").rstrip(".") if isinstance(number, float) else str(number)
            if str(number) in present or token in present:
                problems.append(f"forbidden number {number} present (misheard minimal-pair value)")

    for brand in expect.get("brandsVerbatim", []):
        if not contains(transcript, brand):
            problems.append(f"brand {brand!r} not verbatim")

    if expect.get("lot") and not contains(transcript, expect["lot"]):
        problems.append(f"lot {expect['lot']!r} not verbatim")

    if expect.get("noLatinWords"):
        allow = [*expect.get("allowLatin", []), *expect.get("brandsVerbatim", []), *([expect["lot"]] if expect.get("lot") else [])]
        offenders = latin_offenders(transcript, allow=allow)
        if offenders:
            problems.append(f"romanized/Latin words present: {offenders}")

    for banned in expect.get("forbidden", []):
        if contains(transcript, banned):
            problems.append(f"forbidden {banned!r} present (wrong unit / hallucination)")

    if expect.get("language") and language and language != expect["language"]:
        problems.append(f"language {language!r}≠{expect['language']!r}")

    return problems


# --- Quality tier: LLM-as-judge -------------------------------------------------------------------

JUDGE_ROLE = (
    "You are a strict transcription-quality judge for a clinical memory system. Compare a CANDIDATE "
    "transcript (produced by a speech-to-text model) against the REFERENCE transcript (ground truth: "
    "what was actually said)."
)
JUDGE_RUBRIC = {
    "nativeScript": "1.0 = the candidate is written ENTIRELY in the spoken language's native script "
    "(Persian speech in Persian script); 0.0 = romanized into Latin or translated. Penalize EVERY "
    "romanized Persian word. Latin brand names or spelled-out letters are acceptable.",
    "doseFidelity": "1.0 = every dose / quantity / unit in the reference appears in the candidate with "
    "the SAME value (word or digit form both fine); penalize any wrong, missing, or invented number "
    "heavily — a single wrong dose digit is near 0.",
    "brandLotFidelity": "1.0 = every brand name and lot/batch string in the reference is reproduced "
    "verbatim in the candidate; lower for any altered or dropped brand/lot.",
    "completeness": "1.0 = the candidate captures all clinically meaningful content of the reference "
    "(areas, products, instructions); lower for each meaningful omission.",
    "noHallucination": "1.0 = the candidate adds nothing not supported by the reference; lower for any "
    "invented clinical content, identity, or instruction.",
}


def judge_transcript(reference: str, candidate: str, dimensions: list[str]) -> dict[str, Any]:
    """Score a candidate transcript against the reference via the gateway LLM judge."""
    return judge(role=JUDGE_ROLE, rubric=JUDGE_RUBRIC, dimensions=dimensions, reference=reference, candidate=candidate)


# --- Synthetic cases (run before any recordings exist) --------------------------------------------

# Deterministic gate self-tests: prove the safety matchers catch what they must. Pure Python — these
# run with or without a gateway. Negative cases name a phrase the failure reason must contain.
GATE_SELF_TESTS: list[dict[str, Any]] = [
    {
        "name": "clean fa botox dose passes all gates",
        "transcript": "بیست واحد بوتاکس روی پیشانی زدم",
        "language": "fa",
        "expect": {"containsFa": ["بوتاکس", "واحد"], "containsAny": [["بیست", "۲۰"]], "noLatinWords": True, "language": "fa"},
        "expectGatesPass": True,
    },
    {
        "name": "filler dose with cc + digit number passes",
        "transcript": "یک سی‌سی ژل ژوویدرم توی گونه چپ، ۲۰ واحد",
        "language": "fa",
        "expect": {"containsFa": ["ژل", "سی سی"], "brandsVerbatim": ["ژوویدرم"], "numbers": [20], "noLatinWords": True},
        "expectGatesPass": True,
    },
    {
        "name": "romanized Persian FAILS the no-Latin gate",
        "transcript": "bist vahed botox roo pishani",
        "language": "fa",
        "expect": {"noLatinWords": True},
        "expectGatesPass": False,
        "expectReasonContains": "romanized",
    },
    {
        "name": "missing dose word FAILS the containsAny gate",
        "transcript": "بوتاکس روی پیشانی زدم",
        "language": "fa",
        "expect": {"containsAny": [["بیست", "۲۰"]]},
        "expectGatesPass": False,
        "expectReasonContains": "none of",
    },
    {
        "name": "wrong dose number FAILS the numbers gate",
        "transcript": "سی واحد بوتاکس، ۳۰ واحد",
        "language": "fa",
        "expect": {"numbers": [20]},
        "expectGatesPass": False,
        "expectReasonContains": "number 20",
    },
    {
        "name": "dropped brand FAILS the brandsVerbatim gate",
        "transcript": "یک سی‌سی ژل توی گونه",
        "language": "fa",
        "expect": {"brandsVerbatim": ["ژوویدرم"]},
        "expectGatesPass": False,
        "expectReasonContains": "ژوویدرم",
    },
    {
        "name": "forbidden wrong-unit token is caught",
        "transcript": "بیست میلی‌گرم بوتاکس روی پیشانی",
        "language": "fa",
        "expect": {"forbidden": ["میلی‌گرم"]},
        "expectGatesPass": False,
        "expectReasonContains": "forbidden",
    },
    {
        "name": "Latin brand allowed via allowLatin while romanization still blocked",
        "transcript": "یک سی‌سی Juvederm توی گونه",
        "language": "fa",
        "expect": {"noLatinWords": True, "allowLatin": ["Juvederm"]},
        "expectGatesPass": True,
    },
    {
        "name": "decimal/half dose accepted (نیم and ۰.۵)",
        "transcript": "نیم سی‌سی ژل توی لب، یعنی حدوداً ۰.۵ سی‌سی",
        "language": "fa",
        "expect": {"containsAny": [["نیم", "0.5"]], "numbers": [0.5], "noLatinWords": True},
        "expectGatesPass": True,
    },
    {
        "name": "one-and-a-half as digits (۱.۵) passes the numbers gate",
        "transcript": "یک و نیم سی‌سی ژل، ۱.۵ سی‌سی",
        "language": "fa",
        "expect": {"numbers": [1.5]},
        "expectGatesPass": True,
    },
    {
        "name": "negation preserved — «انجام نشد» must not false-match «انجام شد»",
        "transcript": "امروز فقط مشاوره بود و تزریق انجام نشد",
        "language": "fa",
        "expect": {"containsFa": ["نشد"], "forbidden": ["انجام شد"], "noLatinWords": True},
        "expectGatesPass": True,
    },
    {
        "name": "cross-unit error caught — botox is dosed in واحد, never سی‌سی",
        "transcript": "بیست سی‌سی بوتاکس روی پیشانی",
        "language": "fa",
        "expect": {"forbidden": ["سی‌سی"]},
        "expectGatesPass": False,
        "expectReasonContains": "forbidden",
    },
    {
        "name": "confusable dose ۲۴ correct, forbidden ۲۰ absent → passes both directions",
        "transcript": "بیست و چهار واحد بوتاکس، ۲۴ واحد",
        "language": "fa",
        "expect": {"numbers": [24], "numbersForbidden": [20]},
        "expectGatesPass": True,
    },
    {
        "name": "misheard minimal-pair ۲۰ present FAILS the numbersForbidden gate",
        "transcript": "بیست واحد بوتاکس، ۲۰ واحد",
        "language": "fa",
        "expect": {"numbersForbidden": [20]},
        "expectGatesPass": False,
        "expectReasonContains": "forbidden number",
    },
]

# Judge smoke cases: synthetic (reference, candidate) text pairs that exercise the LLM judge so the
# rubric is validated before any audio exists. Advisory (LLM nondeterminism) — reported, not blocking.
JUDGE_SMOKE_TESTS: list[dict[str, Any]] = [
    {
        "name": "identical clean transcript scores high",
        "reference": "بیست واحد بوتاکس روی پیشانی زدم و یک سی‌سی ژل ژوویدرم توی گونه چپ",
        "candidate": "بیست واحد بوتاکس روی پیشانی زدم و یک سی‌سی ژل ژوویدرم توی گونه چپ",
        "dimensions": ["nativeScript", "doseFidelity", "brandLotFidelity"],
        "expectHigh": True,
    },
    {
        "name": "romanized candidate scores low on nativeScript",
        "reference": "بیست واحد بوتاکس روی پیشانی زدم",
        "candidate": "bist vahed botox rooye pishani zadam",
        "dimensions": ["nativeScript"],
        "expectHigh": False,
    },
    {
        "name": "wrong dose candidate scores low on doseFidelity",
        "reference": "بیست واحد بوتاکس روی پیشانی زدم",
        "candidate": "سی واحد بوتاکس روی پیشانی زدم",
        "dimensions": ["doseFidelity"],
        "expectHigh": False,
    },
]


# --- Runners --------------------------------------------------------------------------------------


def run_gate_self_tests() -> bool:
    """Deterministic safety-matcher self-tests. Returns True iff all behave as authored."""
    print("--- safety-gate self-tests (deterministic, no gateway) ---")
    ok = True
    for index, case in enumerate(GATE_SELF_TESTS, start=1):
        problems = run_gates(case["transcript"], case.get("language"), case["expect"])
        passed = not problems
        as_expected = passed == case["expectGatesPass"]
        if as_expected and not case["expectGatesPass"]:
            needle = case.get("expectReasonContains")
            if needle and not any(needle in problem for problem in problems):
                as_expected = False
        ok = ok and as_expected
        verdict = "OK  " if as_expected else "BUG "
        detail = "gates pass" if passed else f"gates fail: {'; '.join(problems)}"
        print(f"  [{index}] {verdict} {case['name']}  → {detail}")
    print(f"  self-tests: {'all matchers behave correctly' if ok else 'HARNESS BUG — a matcher misbehaved'}")
    return ok


def run_judge_smoke() -> bool:
    """Run the LLM-judge smoke cases. Advisory; a gateway error degrades to a SKIP (returns True)."""
    print("\n--- judge smoke cases (LLM-as-judge on the gateway) ---")
    ok = True
    for index, case in enumerate(JUDGE_SMOKE_TESTS, start=1):
        try:
            result = judge_transcript(case["reference"], case["candidate"], case["dimensions"])
        except Exception as exc:  # noqa: BLE001 — gateway/network: degrade to skip, don't fail.
            print(f"  [{index}] SKIP judge unreachable on {case['name']!r}: {exc!r}")
            return True
        if not result.get("ok"):
            print(f"  [{index}] WARN {case['name']}: {result.get('rationale')}")
            ok = False
            continue
        worst = min_score(result["scores"])
        matched = (worst >= DEFAULT_MIN_SCORE) == case["expectHigh"]
        ok = ok and matched
        want = "≥" if case["expectHigh"] else "<"
        print(f"  [{index}] {'OK  ' if matched else 'MISS'} {case['name']}  → {quality_line(result['scores'], DEFAULT_MIN_SCORE)} (want min {want}{DEFAULT_MIN_SCORE:.2f})")
    return ok


def run_fixtures() -> tuple[int, int, int, int, str | None]:
    """Run real-audio fixtures. Returns (safety_pass, safety_fail, quality_pass, quality_fail, prompt_version)."""
    fixtures = load_fixtures("transcription", AUDIO_SUFFIXES)
    print("\n--- real-audio fixtures ---")
    if not fixtures:
        print("  (no recordings yet — drop clips per the capture manifest to make this real)")
        return 0, 0, 0, 0, None
    safety_pass = safety_fail = quality_pass = quality_fail = 0
    prompt_version: str | None = None
    for index, fixture in enumerate(fixtures, start=1):
        name, spec = fixture["name"], fixture.get("spec")
        if spec is None:
            print(f"  [{index}] SKIP {name}: {fixture.get('error', 'no sibling .json with expected facts')}")
            continue
        context = {**TRANSCRIPTION_CONTEXT, **(spec.get("context") or {})}
        try:
            output = transcribe_audio_content(fixture["media"].read_bytes(), context)
        except Exception as exc:  # noqa: BLE001 — gateway/ffmpeg error: report and stop scoring fixtures.
            print(f"  [{index}] ERROR {name}: transcription failed: {exc!r}")
            print("  SKIP: gateway/ffmpeg unreachable — fixtures not scored. Re-run where reachable.")
            break
        prompt_version = prompt_version or capture_prompt_version(output)
        transcript, language = output.get("transcript") or "", output.get("language")

        problems = run_gates(transcript, language, spec.get("expect") or {})
        known_gap = spec.get("knownGap")
        if spec.get("expect"):
            if problems and known_gap:
                print(f"  [{index}] KNOWN-GAP {name}: {'; '.join(problems)}\n             → {transcript!r}\n             ↳ {known_gap}")
            elif problems:
                safety_fail += 1
                print(f"  [{index}] SAFETY FAIL {name}: {'; '.join(problems)}\n             → {transcript!r}")
            else:
                safety_pass += 1
                print(f"  [{index}] SAFETY PASS {name}  → {transcript!r}")

        judge_spec, reference = spec.get("judge"), spec.get("said")
        if judge_spec and reference:
            dimensions = [d for d in (judge_spec.get("dimensions") or JUDGE_DIMENSIONS) if d in JUDGE_RUBRIC]
            threshold = float(judge_spec.get("minScore", DEFAULT_MIN_SCORE))
            try:
                result = judge_transcript(reference, transcript, dimensions)
            except Exception as exc:  # noqa: BLE001
                print(f"             QUALITY SKIP: judge unreachable: {exc!r}")
                continue
            if not result.get("ok"):
                print(f"             QUALITY WARN: {result.get('rationale')}")
                continue
            if min_score(result["scores"]) >= threshold:
                quality_pass += 1
                tag = "QUALITY PASS"
            else:
                quality_fail += 1
                tag = "QUALITY FAIL"
            print(f"             {tag} ({quality_line(result['scores'], threshold)}) — {result.get('rationale')}")
    return safety_pass, safety_fail, quality_pass, quality_fail, prompt_version


def main() -> int:
    models = env_models("AI_ENGINE_TRANSCRIPTION_MODEL")
    self_tests_ok = run_gate_self_tests()
    if not gateway_configured():
        print("\nSKIP: no AI gateway configured. Gateway-backed transcription + judge not run; "
              "deterministic self-tests above stand.")
        write_scorecard(
            "transcription_eval",
            metrics={"self_tests_ok": int(self_tests_ok), "safety_pass": 0, "safety_fail": 0,
                     "quality_pass": 0, "quality_fail": 0, "cases_total": 0},
            models_under_test=models,
        )
        return 0 if self_tests_ok else 1

    judge_smoke_ok = run_judge_smoke()
    safety_pass, safety_fail, quality_pass, quality_fail, prompt_version = run_fixtures()

    print(f"\n{'=' * 8} TRANSCRIPTION SCORECARD {'=' * 8}")
    print(f"  self-tests:    {'PASS' if self_tests_ok else 'FAIL (harness bug)'}")
    print(f"  judge smoke:   {'PASS' if judge_smoke_ok else 'MISS (advisory)'}")
    print(f"  safety gates:  {safety_pass} pass / {safety_fail} fail  (real fixtures)")
    print(f"  quality (judge): {quality_pass} pass / {quality_fail} below threshold  "
          f"({'blocking' if STRICT_QUALITY else 'advisory'})")
    write_scorecard(
        "transcription_eval",
        metrics={"self_tests_ok": int(self_tests_ok), "judge_smoke_ok": int(judge_smoke_ok),
                 "safety_pass": safety_pass, "safety_fail": safety_fail,
                 "quality_pass": quality_pass, "quality_fail": quality_fail,
                 "cases_total": safety_pass + safety_fail},
        models_under_test=models,
        prompt_version=prompt_version,
    )
    return exit_code(self_tests_ok=self_tests_ok, safety_fail=safety_fail, quality_fail=quality_fail, judge_smoke_ok=judge_smoke_ok)


if __name__ == "__main__":
    raise SystemExit(main())
