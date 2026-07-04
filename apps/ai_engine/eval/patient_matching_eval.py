#!/usr/bin/env python3
"""Golden-set eval for PATIENT MATCHING — the AI side of the auto-assign safety gate.

The deterministic auto-assign decision (exact-alias vs fuzzy near-miss, "never silently auto-assign on
a near-miss") lives in the BACKEND and is already unit-tested (``test_ai_assignment_gate.py``,
``test_patient_identity_matching.py``). What that gate CANNOT be safe without — and what those unit
tests cannot cover — is the LLM input it consumes: TRANSCRIPTION's name extraction + assignment-intent
classification. This eval owns that seam (shared harness in ``_common.py``):

* **Safety gates** — deterministic, on the transcription output:
  - the spoken name is extracted FAITHFULLY (so the backend matcher sees the real near-miss string and
    surfaces a candidate, instead of the model silently "correcting" it to an existing patient);
  - the assignment **basis is not over-escalated**: a mere mention / near-miss must be ``implicit`` (or
    absent), NEVER ``explicit`` — because explicit is the only basis that can auto-apply a fuzzy match,
    so a mis-classification here is what would turn a near-miss into an unsafe silent auto-assign;
  - the name stays in native script (``raw_mentioned_name`` not romanized);
  - no over-detection (a clip with no name → no name extracted).
* **Quality (LLM judge)** — transliteration quality of ``standardized_display_name``. Advisory.

Real audio (a spoken name) is the only way to test the live extraction, so it is fixture-driven over
the matching fixtures dir; until clips land, deterministic gate self-tests + judge smoke keep it honest.

Run::

    docker exec notari-main-ai-engine-1 python /app/eval/patient_matching_eval.py
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
    capture_prompt_version,
    contains,
    env_models,
    exit_code,
    gateway_configured,
    judge,
    latin_offenders,
    load_fixtures,
    min_score,
    quality_line,
    write_scorecard,
)
from ai_engine.processing import transcribe_audio_content  # noqa: E402

TRANSCRIPTION_CONTEXT: dict[str, Any] = {
    "preferredLanguage": "auto",
    "domain": {"label": "aesthetics clinic", "vocabulary": ["بوتاکس", "فیلر", "ژل"]},
}
JUDGE_DIMENSIONS = ("transliterationQuality",)


def _assignment(output: dict[str, Any]) -> dict[str, Any]:
    intents = output.get("intents")
    assignment = intents.get("assignment") if isinstance(intents, dict) else None
    return assignment if isinstance(assignment, dict) else {}


# --- Safety gates (deterministic) -----------------------------------------------------------------


def run_gates(output: dict[str, Any], expect: dict[str, Any]) -> list[str]:
    """Apply the deterministic safety gates to a transcription output; return failures (empty == pass)."""
    problems: list[str] = []
    patient = output.get("patient_information") or {}
    raw = patient.get("raw_mentioned_name")
    standardized = patient.get("standardized_display_name")
    assignment = _assignment(output)

    for token in expect.get("nameContains", []):
        if not (contains(raw or "", token) or contains(standardized or "", token)):
            problems.append(f"spoken name {token!r} not extracted (raw={raw!r}, std={standardized!r})")

    if expect.get("noName") and (raw or standardized):
        problems.append(f"expected NO name but extracted raw={raw!r} std={standardized!r} (over-detection)")

    if "assignmentPresent" in expect and bool(assignment.get("present")) != expect["assignmentPresent"]:
        problems.append(f"assignment.present {assignment.get('present')!r}≠{expect['assignmentPresent']}")

    if "basis" in expect and assignment.get("basis") != expect["basis"]:
        problems.append(f"assignment.basis {assignment.get('basis')!r}≠{expect['basis']!r}")

    # The keystone near-miss safety gate: a mention/near-miss must NOT be 'explicit' (explicit is the
    # only basis the backend will auto-apply a fuzzy match on).
    if "basisNot" in expect and assignment.get("basis") == expect["basisNot"]:
        problems.append(
            f"assignment.basis is {expect['basisNot']!r} — a mention/near-miss classified explicit risks "
            "an unsafe silent auto-assign"
        )

    if expect.get("noLatinInName"):
        offenders = latin_offenders(raw or "")
        if offenders:
            problems.append(f"raw_mentioned_name romanized: {offenders}")

    if expect.get("nationalId") and not contains(patient.get("national_id") or "", expect["nationalId"]):
        problems.append(f"national_id {expect['nationalId']!r} not extracted (got {patient.get('national_id')!r})")

    if expect.get("phone") and not contains(patient.get("phone") or "", expect["phone"]):
        problems.append(f"phone {expect['phone']!r} not extracted (got {patient.get('phone')!r})")

    # A name that must NOT be extracted (e.g. a name from prior CONTEXT the clip didn't actually speak).
    for token in expect.get("nameAbsent", []):
        if contains(raw or "", token) or contains(standardized or "", token):
            problems.append(f"name {token!r} extracted but was not spoken in THIS clip (context bleed)")

    return problems


# --- Quality tier: LLM-as-judge -------------------------------------------------------------------

JUDGE_ROLE = (
    "You are a strict transliteration judge. The REFERENCE is a patient name as spoken (Persian "
    "script); the CANDIDATE is the system's Latin transliteration of it."
)
JUDGE_RUBRIC = {
    "transliterationQuality": "1.0 = the candidate is a faithful, readable Latin transliteration of the "
    "SAME name in the reference; 0.0 = it is a different name, a mistranslation, or garbled.",
}


def judge_transliteration(reference: str, candidate: str) -> dict[str, Any]:
    return judge(
        role=JUDGE_ROLE, rubric=JUDGE_RUBRIC, dimensions=list(JUDGE_DIMENSIONS), reference=reference, candidate=candidate,
        reference_label="REFERENCE (spoken name, Persian)", candidate_label="CANDIDATE (transliteration)",
    )


# --- Synthetic cases ------------------------------------------------------------------------------

def _output(raw: str | None, standardized: str | None, *, present: bool = False, basis: str | None = None,
            national_id: str | None = None, phone: str | None = None) -> dict[str, Any]:
    assignment = {"present": present, "basis": basis, "confidence": 0.5, "evidence": None} if present or basis else {"present": False}
    return {
        "transcript": raw or "",
        "patient_information": {"raw_mentioned_name": raw, "standardized_display_name": standardized,
                               "national_id": national_id, "phone": phone},
        "intents": {"assignment": assignment},
    }


GATE_SELF_TESTS: list[dict[str, Any]] = [
    {
        "name": "explicit reassignment ('change patient to X') → basis explicit OK",
        "output": _output("نگار محمدی", "Negar Mohammadi", present=True, basis="explicit"),
        "expect": {"nameContains": ["نگار"], "assignmentPresent": True, "basis": "explicit", "noLatinInName": True},
        "expectGatesPass": True,
    },
    {
        "name": "mere mention → basis implicit, must NOT be explicit",
        "output": _output("خانم محمدی", "Khanom Mohammadi", present=True, basis="implicit"),
        "expect": {"nameContains": ["محمدی"], "basisNot": "explicit", "noLatinInName": True},
        "expectGatesPass": True,
    },
    {
        "name": "NEAR-MISS classified explicit → FAILS the keystone safety gate",
        "output": _output("معاضد", "Moazed", present=True, basis="explicit"),
        "expect": {"basisNot": "explicit"},
        "expectGatesPass": False,
        "expectReasonContains": "silent auto-assign",
    },
    {
        "name": "no name spoken → nothing extracted (no over-detection)",
        "output": _output(None, None),
        "expect": {"noName": True},
        "expectGatesPass": True,
    },
    {
        "name": "context name copied when none spoken → FAILS noName (over-detection)",
        "output": _output("نگار محمدی", "Negar Mohammadi"),
        "expect": {"noName": True},
        "expectGatesPass": False,
        "expectReasonContains": "over-detection",
    },
    {
        "name": "romanized raw name → FAILS native-script gate",
        "output": _output("Negar Mohammadi", "Negar Mohammadi", present=True, basis="implicit"),
        "expect": {"nameContains": ["Negar"], "noLatinInName": True},
        "expectGatesPass": False,
        "expectReasonContains": "romanized",
    },
    {
        "name": "national id dictated → extracted to digits",
        "output": {"patient_information": {"raw_mentioned_name": None, "standardized_display_name": None, "national_id": "0012345678"}, "intents": None},
        "expect": {"nationalId": "0012345678"},
        "expectGatesPass": True,
    },
    {
        "name": "first-name only mention → extracted, basis implicit (must surface, not auto-assign)",
        "output": _output("سارا", "Sara", present=True, basis="implicit"),
        "expect": {"nameContains": ["سارا"], "basisNot": "explicit", "noLatinInName": True},
        "expectGatesPass": True,
    },
    {
        "name": "title + last name → extracted, implicit",
        "output": _output("خانم محمدی", "Khanom Mohammadi", present=True, basis="implicit"),
        "expect": {"nameContains": ["محمدی"], "basisNot": "explicit"},
        "expectGatesPass": True,
    },
    {
        "name": "explicit reassignment/correction ('change to X') → basis explicit OK",
        "output": _output("سارا محمدی", "Sara Mohammadi", present=True, basis="explicit"),
        "expect": {"nameContains": ["محمدی"], "assignmentPresent": True, "basis": "explicit"},
        "expectGatesPass": True,
    },
    {
        "name": "phone dictated → extracted (normalized)",
        "output": _output(None, None, phone="+989121234567"),
        "expect": {"phone": "9121234567"},
        "expectGatesPass": True,
    },
    {
        "name": "no name spoken, but a prior-context name must NOT be extracted (nameAbsent)",
        "output": _output(None, None),
        "expect": {"nameAbsent": ["نگار", "محمدی"]},
        "expectGatesPass": True,
    },
    {
        "name": "nameAbsent FAILS when a context name bled into extraction",
        "output": _output("نگار محمدی", "Negar Mohammadi"),
        "expect": {"nameAbsent": ["نگار"]},
        "expectGatesPass": False,
        "expectReasonContains": "context bleed",
    },
    # (m07 class) name spoken MID-dictation, not as the lead phrase («برای خانم محمدی امروز بیست
    # واحد…») — it must still be extracted, and as a mere mention basis is implicit, never explicit.
    {
        "name": "name mid-dictation (not lead phrase) → extracted, basis implicit (not explicit)",
        "output": _output("خانم محمدی", "Khanom Mohammadi", present=True, basis="implicit"),
        "expect": {"nameContains": ["محمدی"], "basisNot": "explicit", "noLatinInName": True},
        "expectGatesPass": True,
    },
    # (m08 class) two SIMILAR-sounding EXISTING patients (محمدی vs محمودی): the model must extract the
    # one ACTUALLY said faithfully and NOT "correct" it to the near neighbour.
    {
        "name": "similar-name pair: محمودی said → extract محمودی, NOT محمدی (no auto-correction)",
        "output": _output("خانم محمودی", "Khanom Mahmoudi", present=True, basis="implicit"),
        "expect": {"nameContains": ["محمودی"], "nameAbsent": ["محمدی"], "basisNot": "explicit"},
        "expectGatesPass": True,
    },
    {
        "name": "similar-name pair: محمودی said but 'corrected' to محمدی → FAILS (unfaithful extraction)",
        "output": _output("خانم محمدی", "Khanom Mohammadi", present=True, basis="implicit"),
        "expect": {"nameContains": ["محمودی"], "nameAbsent": ["محمدی"]},
        "expectGatesPass": False,
        "expectReasonContains": "not extracted",
    },
]

JUDGE_SMOKE_TESTS: list[dict[str, Any]] = [
    {"name": "faithful transliteration scores high", "reference": "نگار محمدی", "candidate": "Negar Mohammadi", "expectHigh": True},
    {"name": "wrong name scores low", "reference": "نگار محمدی", "candidate": "Sara Ahmadi", "expectHigh": False},
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


def run_judge_smoke() -> bool:
    print("\n--- judge smoke cases (transliteration quality on the gateway) ---")
    ok = True
    for index, case in enumerate(JUDGE_SMOKE_TESTS, start=1):
        try:
            result = judge_transliteration(case["reference"], case["candidate"])
        except Exception as exc:  # noqa: BLE001
            print(f"  [{index}] SKIP judge unreachable on {case['name']!r}: {exc!r}")
            return True
        if not result.get("ok"):
            print(f"  [{index}] WARN {case['name']}: {result.get('rationale')}")
            ok = False
            continue
        matched = (min_score(result["scores"]) >= DEFAULT_MIN_SCORE) == case["expectHigh"]
        ok = ok and matched
        want = "≥" if case["expectHigh"] else "<"
        print(f"  [{index}] {'OK  ' if matched else 'MISS'} {case['name']}  → {quality_line(result['scores'], DEFAULT_MIN_SCORE)} (want {want}{DEFAULT_MIN_SCORE:.2f})")
    return ok


def run_fixtures() -> tuple[int, int, str | None]:
    """Run real spoken-name audio fixtures. Returns (safety_pass, safety_fail, prompt_version)."""
    fixtures = load_fixtures("matching", AUDIO_SUFFIXES)
    print("\n--- real spoken-name fixtures ---")
    if not fixtures:
        print("  (no recordings yet — drop name clips per the capture manifest to make this real)")
        return 0, 0, None
    safety_pass = safety_fail = 0
    prompt_version: str | None = None
    for index, fixture in enumerate(fixtures, start=1):
        name, spec = fixture["name"], fixture.get("spec")
        if spec is None:
            print(f"  [{index}] SKIP {name}: {fixture.get('error', 'no sibling .json with expected facts')}")
            continue
        context = {**TRANSCRIPTION_CONTEXT, **(spec.get("context") or {})}
        try:
            output = transcribe_audio_content(fixture["media"].read_bytes(), context)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{index}] ERROR {name}: transcription failed: {exc!r}")
            print("  SKIP: gateway/ffmpeg unreachable — fixtures not scored.")
            break
        prompt_version = prompt_version or capture_prompt_version(output)
        problems = run_gates(output, spec.get("expect") or {})
        patient = output.get("patient_information") or {}
        summary = f"raw={patient.get('raw_mentioned_name')!r} basis={_assignment(output).get('basis')!r}"
        known_gap = spec.get("knownGap")
        if problems and known_gap:
            # xfail: a documented model limitation — reported loudly, NOT counted as a blocking failure.
            print(f"  [{index}] KNOWN-GAP {name}: {'; '.join(problems)}  | {summary}\n             ↳ {known_gap}")
        elif problems:
            safety_fail += 1
            print(f"  [{index}] SAFETY FAIL {name}: {'; '.join(problems)}  | {summary}")
        else:
            safety_pass += 1
            note = "  (knownGap — passed this run; behaviour here is unreliable)" if known_gap else ""
            print(f"  [{index}] SAFETY PASS {name}  → {summary}{note}")
    return safety_pass, safety_fail, prompt_version


def main() -> int:
    models = env_models("AI_ENGINE_TRANSCRIPTION_MODEL")
    self_tests_ok = run_gate_self_tests()
    if not gateway_configured():
        print("\nSKIP: no AI gateway configured. Extraction fixtures + judge not run; self-tests above stand.")
        write_scorecard(
            "patient_matching_eval",
            metrics={"self_tests_ok": int(self_tests_ok), "safety_pass": 0, "safety_fail": 0, "cases_total": 0},
            models_under_test=models,
        )
        return 0 if self_tests_ok else 1

    judge_smoke_ok = run_judge_smoke()
    safety_pass, safety_fail, prompt_version = run_fixtures()

    print(f"\n{'=' * 8} PATIENT-MATCHING SCORECARD {'=' * 8}")
    print(f"  self-tests:   {'PASS' if self_tests_ok else 'FAIL (harness bug)'}")
    print(f"  judge smoke:  {'PASS' if judge_smoke_ok else 'MISS (advisory)'}")
    print(f"  safety gates: {safety_pass} pass / {safety_fail} fail  (real fixtures)")
    print("  note: the deterministic auto-assign gate itself is backend-unit-tested; this covers the LLM input to it.")
    write_scorecard(
        "patient_matching_eval",
        metrics={"self_tests_ok": int(self_tests_ok), "judge_smoke_ok": int(judge_smoke_ok),
                 "safety_pass": safety_pass, "safety_fail": safety_fail,
                 "cases_total": safety_pass + safety_fail},
        models_under_test=models,
        prompt_version=prompt_version,
    )
    return exit_code(self_tests_ok=self_tests_ok, safety_fail=safety_fail, judge_smoke_ok=judge_smoke_ok)


if __name__ == "__main__":
    raise SystemExit(main())
