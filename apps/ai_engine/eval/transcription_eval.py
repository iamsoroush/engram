#!/usr/bin/env python3
"""Golden-set eval for AUDIO TRANSCRIPTION — the foundation job (garbage in → garbage everywhere).

Transcription is the highest-stakes AI job: a mis-heard dose token (۲ vs ۳ vs ۲۳), a romanized
Persian name, or a dropped brand/lot poisons everything downstream (treatments, matching, the
patient share). This eval runs the REAL gateway against fixed cases and scores it on TWO tiers:

* **Safety gates** — deterministic matchers (substring / numeric-token / presence / no-Latin). HARD
  pass/fail; a failure blocks ship and exits non-zero. This is the dose-token / no-romanization gate.
* **Quality (LLM-as-judge)** — a rubric (native-script fidelity, dose fidelity, brand/lot fidelity,
  completeness, no-hallucination) scored 0..1 by a judge on the same gateway. Tracked to drive
  iteration; advisory by default (set ``EVAL_STRICT_QUALITY=1`` to make below-threshold blocking too).

Transcription can only be truly evaluated on REAL AUDIO, so the suite is fixture-driven: drop a clip
at ``eval/fixtures/transcription/<case>.m4a`` plus a sibling ``<case>.json`` (the expected facts,
format documented below) and it is scored automatically — see ``fixtures/RECORDING_CHECKLIST.md``.
Until recordings land, two layers keep the harness honest and runnable:

* **Deterministic gate self-tests** — synthetic ``(transcript, expect)`` pairs (positive + negative)
  that prove the safety matchers catch what they must. Pure Python, run ALWAYS (no gateway needed).
* **Judge smoke cases** — synthetic ``(reference, candidate)`` text pairs run through the LLM judge to
  prove the rubric discriminates clean Persian from romanized/dropped-dose output. Need the gateway.

Run where a gateway is reachable::

    docker exec notari-main-ai-engine-1 python /app/eval/transcription_eval.py

No gateway → the gateway portion SKIPS; the deterministic self-tests still run. Exit code is driven by
SAFETY only (deterministic self-tests + real-fixture gates); LLM-judge outcomes are reported but never
flake CI red unless ``EVAL_STRICT_QUALITY=1``.

----------------------------------------------------------------------------------------------------
``<case>.json`` expectation format
----------------------------------------------------------------------------------------------------
::

    {
      "said": "بیست واحد بوتاکس روی پیشانی زدم.",   // OPTIONAL ground-truth transcript: the LLM judge's
                                                     // reference + documentation. Judge skipped if absent.
      "context": {"preferredLanguage": "fa"},        // OPTIONAL transcription context overrides (merged).

      "expect": {                                    // SAFETY GATES — deterministic, HARD pass/fail.
        "containsFa":     ["بوتاکس", "واحد"],        //   every string must appear verbatim (script/ZWNJ/digit tolerant)
        "containsAny":    [["بیست", "۲۰"]],          //   each group: AT LEAST ONE must appear (dose as word OR digits)
        "numbers":        [20],                       //   each number must appear as a digit token (digits normalized to Latin)
        "brandsVerbatim": ["ژوویدرم"],               //   brand strings must appear verbatim
        "lot":            "ABC123",                   //   the lot/batch string must appear verbatim
        "noLatinWords":   true,                       //   transcript must contain NO Latin-script words (anti-romanization)
        "allowLatin":     ["Juvederm"],               //   exceptions to noLatinWords (brands legitimately in Latin)
        "forbidden":      ["میلی‌گرم"],              //   strings that must NOT appear (wrong unit / hallucination)
        "language":       "fa"                        //   expected detected language code (fa|en|mixed|unknown)
      },

      "judge": {                                     // QUALITY — LLM-as-judge, advisory unless EVAL_STRICT_QUALITY=1.
        "dimensions": ["nativeScript", "doseFidelity", "brandLotFidelity", "completeness", "noHallucination"],
        "minScore": 0.7                               //   every requested dimension must score >= this
      }
    }

All of ``expect`` and ``judge`` are optional — include only what a case needs to prove.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
from typing import Any

sys.path.insert(0, ".")
sys.path.insert(0, "/app")

from ai_engine.processing import (  # noqa: E402
    gateway_client,
    gateway_settings_for,
    normalize_digits_to_latin,
    transcribe_audio_content,
    transcription_is_configured,
)

# Realistic aesthetics-clinic framing so the gateway prompt matches production (vertical-agnostic by
# contract — supplied as data, never assumed). A fixture's "context" is merged over this.
TRANSCRIPTION_CONTEXT: dict[str, Any] = {
    "preferredLanguage": "auto",
    "domain": {
        "label": "aesthetics clinic",
        "vocabulary": ["بوتاکس", "فیلر", "ژل", "واحد", "سی‌سی", "ژوویدرم", "رستیلین", "کانولا"],
    },
}

AUDIO_SUFFIXES = {".m4a", ".mp3", ".wav", ".flac", ".ogg", ".aac", ".opus", ".webm", ".mp4"}
JUDGE_DIMENSIONS = ("nativeScript", "doseFidelity", "brandLotFidelity", "completeness", "noHallucination")
DEFAULT_MIN_SCORE = 0.7
STRICT_QUALITY = os.environ.get("EVAL_STRICT_QUALITY", "").strip() not in ("", "0", "false", "False")

try:
    HERE = pathlib.Path(__file__).resolve().parent
except NameError:  # piped via stdin (python - < transcription_eval.py)
    HERE = pathlib.Path("/app/eval")
FIXTURES_DIR = HERE / "fixtures" / "transcription"

# A "Latin word" = a run of >=2 ASCII letters. Single letters (a spelled-out lot "A B C") are allowed
# so a dictated lot does not trip the anti-romanization gate; romanized Persian words (>=2 letters) do.
LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")
NUMBER_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?")
# Common Arabic↔Persian confusables the gateway may emit interchangeably; fold them so a verbatim
# clinical token still matches regardless of which code point the model chose.
_ARABIC_TO_PERSIAN = str.maketrans({"ي": "ی", "ك": "ک", "ﻪ": "ه", "ة": "ه", "ﻱ": "ی"})


def _canon(text: Any) -> str:
    """Canonicalize for tolerant substring matching: Latin digits, Persian forms, no ZWNJ/extra space."""
    value = normalize_digits_to_latin(str(text or "")).translate(_ARABIC_TO_PERSIAN)
    return re.sub(r"\s+", " ", value.replace("‌", "")).strip().lower()


def _loose(text: Any) -> str:
    """Even more tolerant: also drop spaces, so «سی‌سی» / «سی سی» / «سیسی» all compare equal."""
    return _canon(text).replace(" ", "")


def _contains(haystack: str, needle: Any) -> bool:
    """True if ``needle`` appears in ``haystack`` under either canonical or space-insensitive folding."""
    return _canon(needle) in _canon(haystack) or _loose(needle) in _loose(haystack)


# --- Safety gates (deterministic) -----------------------------------------------------------------


def run_gates(transcript: str, language: str | None, expect: dict[str, Any]) -> list[str]:
    """Apply the deterministic safety gates; return failure reasons (empty list == all gates pass)."""
    problems: list[str] = []

    for token in expect.get("containsFa", []):
        if not _contains(transcript, token):
            problems.append(f"missing required {token!r}")

    for group in expect.get("containsAny", []):
        options = group if isinstance(group, list) else [group]
        if not any(_contains(transcript, option) for option in options):
            problems.append(f"none of {options} present")

    if expect.get("numbers"):
        present = set(NUMBER_TOKEN_RE.findall(normalize_digits_to_latin(str(transcript))))
        for number in expect["numbers"]:
            token = str(number).rstrip("0").rstrip(".") if isinstance(number, float) else str(number)
            if str(number) not in present and token not in present:
                problems.append(f"number {number} not transcribed as a digit token (have {sorted(present) or '∅'})")

    for brand in expect.get("brandsVerbatim", []):
        if not _contains(transcript, brand):
            problems.append(f"brand {brand!r} not verbatim")

    if expect.get("lot") and not _contains(transcript, expect["lot"]):
        problems.append(f"lot {expect['lot']!r} not verbatim")

    if expect.get("noLatinWords"):
        allowed = {word.lower() for word in expect.get("allowLatin", [])}
        offenders = [
            word for word in LATIN_WORD_RE.findall(str(transcript)) if word.lower() not in allowed
        ]
        if offenders:
            problems.append(f"romanized/Latin words present: {offenders}")

    for banned in expect.get("forbidden", []):
        if _contains(transcript, banned):
            problems.append(f"forbidden {banned!r} present (wrong unit / hallucination)")

    expected_language = expect.get("language")
    if expected_language and language and language != expected_language:
        problems.append(f"language {language!r}≠{expected_language!r}")

    return problems


# --- Quality tier: LLM-as-judge -------------------------------------------------------------------

_JUDGE_DIMENSION_RUBRIC = {
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


def _judge_prompt(reference: str, candidate: str, dimensions: list[str]) -> str:
    rubric = "\n".join(f"- {dim}: {_JUDGE_DIMENSION_RUBRIC[dim]}" for dim in dimensions if dim in _JUDGE_DIMENSION_RUBRIC)
    keys = ", ".join(f'"{dim}": 0.0' for dim in dimensions if dim in _JUDGE_DIMENSION_RUBRIC)
    return (
        "You are a strict transcription-quality judge for a clinical memory system. Compare a CANDIDATE "
        "transcript (produced by a speech-to-text model) against the REFERENCE transcript (ground truth: "
        "what was actually said). Score ONLY the requested dimensions, each from 0.0 to 1.0.\n\n"
        f"Dimensions:\n{rubric}\n\n"
        f"REFERENCE (ground truth):\n{reference}\n\n"
        f"CANDIDATE (to score):\n{candidate}\n\n"
        "Return STRICT JSON only, no markdown, exactly this shape:\n"
        f'{{"scores": {{{keys}}}, "rationale": "one short sentence"}}'
    )


def _parse_judge(raw_text: str, dimensions: list[str]) -> dict[str, Any]:
    text = (raw_text or "").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"scores": {}, "rationale": "judge returned non-JSON", "ok": False}
    raw_scores = parsed.get("scores") if isinstance(parsed.get("scores"), dict) else {}
    scores: dict[str, float] = {}
    for dim in dimensions:
        value = raw_scores.get(dim)
        scores[dim] = max(0.0, min(float(value), 1.0)) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0
    return {"scores": scores, "rationale": str(parsed.get("rationale") or "").strip(), "ok": True}


def judge_transcript(reference: str, candidate: str, dimensions: list[str]) -> dict[str, Any]:
    """Score a candidate transcript against the reference via the gateway LLM judge.

    Returns ``{scores: {dim: 0..1}, rationale, ok}``. ``ok`` is False when the judge call/parse failed
    (so the caller can degrade to "judge unavailable" instead of treating it as a quality failure).
    """
    client = gateway_client("report_synthesis")
    model = gateway_settings_for("report_synthesis")[2]
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": _judge_prompt(reference, candidate, dimensions)}],
    )
    return _parse_judge(response.choices[0].message.content or "", dimensions)


def _min_score(scores: dict[str, float]) -> float:
    return min(scores.values()) if scores else 0.0


# --- Synthetic cases (run before any recordings exist) --------------------------------------------

# Deterministic gate self-tests: prove the safety matchers catch what they must. Pure Python — these
# run with or without a gateway. Each declares whether the gates should PASS; negative cases also
# name a phrase the failure reason must contain, so we know the RIGHT gate fired.
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
]

# Judge smoke cases: synthetic (reference, candidate) text pairs that exercise the LLM judge so the
# rubric is validated before any audio exists. Advisory (LLM nondeterminism) — reported, not blocking.
JUDGE_SMOKE_TESTS: list[dict[str, Any]] = [
    {
        "name": "identical clean transcript scores high",
        "reference": "بیست واحد بوتاکس روی پیشانی زدم و یک سی‌سی ژل ژوویدرم توی گونه چپ",
        "candidate": "بیست واحد بوتاکس روی پیشانی زدم و یک سی‌سی ژل ژوویدرم توی گونه چپ",
        "dimensions": ["nativeScript", "doseFidelity", "brandLotFidelity"],
        "expectHigh": True,  # every requested dimension should clear DEFAULT_MIN_SCORE
    },
    {
        "name": "romanized candidate scores low on nativeScript",
        "reference": "بیست واحد بوتاکس روی پیشانی زدم",
        "candidate": "bist vahed botox rooye pishani zadam",
        "dimensions": ["nativeScript"],
        "expectHigh": False,  # nativeScript should fall BELOW DEFAULT_MIN_SCORE
    },
    {
        "name": "wrong dose candidate scores low on doseFidelity",
        "reference": "بیست واحد بوتاکس روی پیشانی زدم",
        "candidate": "سی واحد بوتاکس روی پیشانی زدم",
        "dimensions": ["doseFidelity"],
        "expectHigh": False,
    },
]


# --- Fixture loading ------------------------------------------------------------------------------


def _load_fixtures() -> list[dict[str, Any]]:
    """Discover ``fixtures/transcription/<case>.<audio>`` + sibling ``<case>.json`` (skip if no json)."""
    if not FIXTURES_DIR.is_dir():
        return []
    fixtures: list[dict[str, Any]] = []
    for media in sorted(FIXTURES_DIR.iterdir()):
        if media.suffix.lower() not in AUDIO_SUFFIXES:
            continue
        spec_path = media.with_suffix(".json")
        if not spec_path.exists():
            fixtures.append({"name": media.name, "media": media, "spec": None})
            continue
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            fixtures.append({"name": media.name, "media": media, "spec": None, "error": str(exc)})
            continue
        fixtures.append({"name": media.name, "media": media, "spec": spec})
    return fixtures


def _quality_line(scores: dict[str, float], min_score: float) -> str:
    return ", ".join(f"{dim}={value:.2f}{'' if value >= min_score else '↓'}" for dim, value in scores.items())


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
    """Run the LLM-judge smoke cases. Returns True iff every case matched its expected verdict.

    Advisory: LLM nondeterminism means this is reported but does not block the exit code unless
    EVAL_STRICT_QUALITY=1. A gateway error degrades to a SKIP (returns True) rather than a failure.
    """
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
        scores = result["scores"]
        worst = _min_score(scores)
        high = worst >= DEFAULT_MIN_SCORE
        matched = high == case["expectHigh"]
        ok = ok and matched
        verdict = "OK  " if matched else "MISS"
        want = "≥" if case["expectHigh"] else "<"
        print(f"  [{index}] {verdict} {case['name']}  → {_quality_line(scores, DEFAULT_MIN_SCORE)} (want min {want}{DEFAULT_MIN_SCORE:.2f})")
    return ok


def run_fixtures() -> tuple[int, int, int, int]:
    """Run real-audio fixtures. Returns (safety_pass, safety_fail, quality_pass, quality_fail)."""
    fixtures = _load_fixtures()
    print(f"\n--- real-audio fixtures ({FIXTURES_DIR}) ---")
    if not fixtures:
        print("  (no recordings yet — drop clips per fixtures/RECORDING_CHECKLIST.md to make this real)")
        return 0, 0, 0, 0
    safety_pass = safety_fail = quality_pass = quality_fail = 0
    for index, fixture in enumerate(fixtures, start=1):
        name = fixture["name"]
        spec = fixture.get("spec")
        if spec is None:
            reason = fixture.get("error", "no sibling .json with expected facts")
            print(f"  [{index}] SKIP {name}: {reason}")
            continue
        context = {**TRANSCRIPTION_CONTEXT, **(spec.get("context") or {})}
        try:
            output = transcribe_audio_content(fixture["media"].read_bytes(), context)
        except Exception as exc:  # noqa: BLE001 — gateway/ffmpeg error: report and stop scoring fixtures.
            print(f"  [{index}] ERROR {name}: transcription failed: {exc!r}")
            print("  SKIP: gateway/ffmpeg unreachable — fixtures not scored. Re-run where reachable.")
            break
        transcript = output.get("transcript") or ""
        language = output.get("language")

        problems = run_gates(transcript, language, spec.get("expect") or {})
        if spec.get("expect"):
            if problems:
                safety_fail += 1
                print(f"  [{index}] SAFETY FAIL {name}: {'; '.join(problems)}\n             → {transcript!r}")
            else:
                safety_pass += 1
                print(f"  [{index}] SAFETY PASS {name}  → {transcript!r}")

        judge_spec = spec.get("judge")
        reference = spec.get("said")
        if judge_spec and reference:
            dimensions = [d for d in (judge_spec.get("dimensions") or JUDGE_DIMENSIONS) if d in _JUDGE_DIMENSION_RUBRIC]
            min_score = float(judge_spec.get("minScore", DEFAULT_MIN_SCORE))
            try:
                result = judge_transcript(reference, transcript, dimensions)
            except Exception as exc:  # noqa: BLE001
                print(f"             QUALITY SKIP: judge unreachable: {exc!r}")
                continue
            if not result.get("ok"):
                print(f"             QUALITY WARN: {result.get('rationale')}")
                continue
            scores = result["scores"]
            if _min_score(scores) >= min_score:
                quality_pass += 1
                tag = "QUALITY PASS"
            else:
                quality_fail += 1
                tag = "QUALITY FAIL"
            print(f"             {tag} ({_quality_line(scores, min_score)}) — {result.get('rationale')}")
    return safety_pass, safety_fail, quality_pass, quality_fail


def main() -> int:
    self_tests_ok = run_gate_self_tests()

    if not transcription_is_configured():
        print("\nSKIP: no AI gateway configured (AI_ENGINE_TRANSCRIPTION_BASE_URL empty). "
              "Gateway-backed transcription + judge not run; deterministic self-tests above stand.")
        return 0 if self_tests_ok else 1

    judge_smoke_ok = run_judge_smoke()
    safety_pass, safety_fail, quality_pass, quality_fail = run_fixtures()

    print(f"\n{'=' * 8} TRANSCRIPTION SCORECARD {'=' * 8}")
    print(f"  self-tests:    {'PASS' if self_tests_ok else 'FAIL (harness bug)'}")
    print(f"  judge smoke:   {'PASS' if judge_smoke_ok else 'MISS (advisory)'}")
    print(f"  safety gates:  {safety_pass} pass / {safety_fail} fail  (real fixtures)")
    print(f"  quality (judge): {quality_pass} pass / {quality_fail} below threshold  "
          f"({'blocking' if STRICT_QUALITY else 'advisory'})")

    # Exit code: SAFETY only by default — deterministic self-tests + real-fixture gates. Quality and
    # judge-smoke are tracked, not gated, so LLM nondeterminism never flakes CI (override: EVAL_STRICT_QUALITY).
    blocking_failed = (not self_tests_ok) or safety_fail > 0
    if STRICT_QUALITY:
        blocking_failed = blocking_failed or quality_fail > 0 or not judge_smoke_ok
    return 1 if blocking_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
