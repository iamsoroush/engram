#!/usr/bin/env python3
"""Golden-set eval for QA REPLY VOICE-EDIT (`qa_revise`, AES-402) — revise-vs-replace from a voice note.

`qa_revise` takes the doctor's spoken note + the current draft and returns strict JSON
``{mode: revise|replace, reply}``. The input is a VOICE NOTE, so scoring is necessarily
**fixture-driven real audio**: clips ``r01–r10`` are recorded by the user/clinician (never
auto-generated) and land under ``eval/fixtures/qa_revise/`` with a sibling ``.json`` spec (a fixed
``currentDraft`` + expectations). Until they land the module is **harness-green** on:

* **parser self-tests** — ``parse_qa_revise_output`` on fenced JSON / non-JSON / missing reply / bad
  mode → the fallback path (the "unusable → keep the current draft" contract).
* **gate self-tests** — deterministic checks over synthetic ``{mode, reply}`` outputs: mode
  classification, numbers-preserved (a revise must not drop/alter a dose), forbidden/contains,
  native script, sign-off.
* **judge smoke** — a clean revise scores high, a botched one (dropped escalation / altered dose) low.

Run::

    docker exec engram-main-ai-engine-1 python /app/eval/qa_revise_eval.py
    # with staged clips:  scripts/eval-fixtures.sh run   (see RECORDING_CHECKLIST.md → qa_revise r01–r10)

No gateway → fixture cases SKIP; parser + gate self-tests still run. Exit = SAFETY only unless
EVAL_STRICT_QUALITY=1.
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
from ai_engine.processing import completed_qa_revise_output, parse_qa_revise_output  # noqa: E402

JUDGE_DIMENSIONS = ("instructionFollowed", "contentPreserved", "escalationPreserved", "languageMatch")


# --- Deterministic gates over a {mode, reply} output ----------------------------------------------


def run_gates(output: dict[str, Any], current_draft: str, expect: dict[str, Any]) -> list[str]:
    """Deterministic HARD gates on a voice-edit output. Returns problems (empty == pass)."""
    problems: list[str] = []
    reply = str(output.get("reply") or "")
    mode = output.get("mode")

    if not reply.strip():
        problems.append("empty reply")
        return problems
    if expect.get("mode") and mode != expect["mode"]:
        problems.append(f"mode {mode!r} != expected {expect['mode']!r}")

    # numbers-preserved: on a revise the clinical numbers in the draft must survive (a doctor asking to
    # shorten/warm must not drop a dose). Only enforced when the spec asks (a `replace` may legitimately
    # drop them).
    if expect.get("numbersPreserved"):
        missing = number_tokens(current_draft) - number_tokens(reply)
        if missing:
            problems.append(f"dropped numbers {sorted(missing)} from the draft")
    # no-invented-numbers: a revise/replace must not introduce a number not in the draft OR the spec's
    # dictated numbers (the spoken note can add a dose the doctor states).
    allowed = number_tokens(current_draft) | {str(n) for n in expect.get("allowNumbers", [])}
    invented = number_tokens(reply) - allowed
    if expect.get("noInventedNumbers") and invented:
        problems.append(f"invented numbers {sorted(invented)} not in draft/dictation")

    for token in expect.get("contains", []):
        if not contains(reply, token):
            problems.append(f"missing {token!r}")
    for group in expect.get("containsAny", []):
        options = group if isinstance(group, list) else [group]
        if not any(contains(reply, option) for option in options):
            problems.append(f"none of {options} present")
    for banned in expect.get("forbidden", []):
        if contains(reply, banned):
            problems.append(f"forbidden {banned!r} present")
    if expect.get("noLatinWords"):
        offenders = latin_offenders(reply, allow=expect.get("allowLatin", []))
        if offenders:
            problems.append(f"romanized/Latin words present: {offenders}")

    return problems


# --- Parser self-tests (no gateway) ---------------------------------------------------------------


def run_parser_self_tests() -> bool:
    print("--- parser self-tests (parse_qa_revise_output, no gateway) ---")
    cases = [
        ("plain JSON", '{"mode":"revise","reply":"سلام"}', {"mode": "revise", "reply": "سلام"}),
        ("fenced JSON", '```json\n{"mode":"replace","reply":"جدید"}\n```', {"mode": "replace", "reply": "جدید"}),
        ("bad mode coerced to revise", '{"mode":"bogus","reply":"x"}', {"mode": "revise", "reply": "x"}),
        ("non-JSON → None (fallback)", "not json at all", None),
        ("missing reply → None (fallback)", '{"mode":"revise"}', None),
        ("empty reply → None (fallback)", '{"mode":"revise","reply":"  "}', None),
    ]
    ok = True
    for index, (name, raw, expected) in enumerate(cases, start=1):
        got = parse_qa_revise_output(raw)
        passed = got == expected
        ok = ok and passed
        print(f"  [{index}] {'OK  ' if passed else 'BUG '} {name} → {got}")
    print(f"  parser self-tests: {'all behave correctly' if ok else 'HARNESS BUG'}")
    return ok


# --- Gate self-tests (synthetic outputs) ----------------------------------------------------------

GATE_SELF_TESTS: list[dict[str, Any]] = [
    {
        "name": "revise keeps numbers + shortens → passes",
        "output": {"mode": "revise", "reply": "سلام، ورم خفیف بعد از ۲۰ واحد بوتاکس طبیعی است. — دکتر دمو"},
        "draft": "سلام سارا، ورم خفیف بعد از ۲۰ واحد بوتاکس در روزهای اول طبیعی است. نگران نباشید. — دکتر دمو",
        "expect": {"mode": "revise", "numbersPreserved": True, "contains": ["دکتر دمو"]},
        "expectPass": True,
    },
    {
        "name": "revise dropped a dose → FAILS numbers-preserved",
        "output": {"mode": "revise", "reply": "سلام، ورم طبیعی است. — دکتر دمو"},
        "draft": "سلام، ورم بعد از ۲۰ واحد بوتاکس طبیعی است. — دکتر دمو",
        "expect": {"mode": "revise", "numbersPreserved": True},
        "expectPass": False,
        "expectReason": "dropped numbers",
    },
    {
        "name": "wrong mode → FAILS mode gate",
        "output": {"mode": "revise", "reply": "متن کاملاً جدید. — دکتر دمو"},
        "draft": "متن قبلی. — دکتر دمو",
        "expect": {"mode": "replace"},
        "expectPass": False,
        "expectReason": "mode",
    },
    {
        "name": "dropped escalation tail → FAILS contains",
        "output": {"mode": "revise", "reply": "نگران نباش، طبیعی است. — دکتر دمو"},
        "draft": "طبیعی است. اگر بدتر شد با کلینیک تماس بگیر. — دکتر دمو",
        "expect": {"mode": "revise", "contains": ["کلینیک"]},
        "expectPass": False,
        "expectReason": "کلینیک",
    },
    {
        "name": "reply flips to English → FAILS no-Latin",
        "output": {"mode": "revise", "reply": "Hi Sara, mild swelling is normal. — Dr. Demo"},
        "draft": "سلام سارا، ورم خفیف طبیعی است. — دکتر دمو",
        "expect": {"mode": "revise", "noLatinWords": True},
        "expectPass": False,
        "expectReason": "romanized",
    },
]


def run_gate_self_tests() -> bool:
    print("\n--- gate self-tests (synthetic outputs, no gateway) ---")
    ok = True
    for index, case in enumerate(GATE_SELF_TESTS, start=1):
        problems = run_gates(case["output"], case["draft"], case["expect"])
        passed = not problems
        as_expected = passed == case["expectPass"]
        if as_expected and not case["expectPass"]:
            needle = case.get("expectReason")
            if needle and not any(needle in item for item in problems):
                as_expected = False
        ok = ok and as_expected
        detail = "gates pass" if passed else f"gates fail: {'; '.join(problems)}"
        print(f"  [{index}] {'OK  ' if as_expected else 'BUG '} {case['name']}  → {detail}")
    print(f"  gate self-tests: {'all matchers behave correctly' if ok else 'HARNESS BUG'}")
    return ok


# --- Quality tier: LLM-as-judge -------------------------------------------------------------------

JUDGE_ROLE = (
    "You are a strict clinical patient-communication judge. A doctor recorded a voice note to edit a "
    "reply draft. Score the CANDIDATE final reply against the REFERENCE (the current draft + what the "
    "voice note asked for)."
)
JUDGE_RUBRIC = {
    "instructionFollowed": "1.0 = the reply reflects exactly what the voice note asked (revise the draft or replace it); lower otherwise.",
    "contentPreserved": "1.0 = on a revise, the clinical content/numbers of the draft are preserved except what was asked to change; lower for lost facts.",
    "escalationPreserved": "1.0 = any clinic-contact / escalation guidance in the draft survives unless explicitly removed; lower if safety guidance is dropped.",
    "languageMatch": "1.0 = reply stays in the patient's language, native script; lower for a language flip or romanization.",
}


def judge_reply(reference: str, candidate: str, dimensions: list[str]) -> dict[str, Any]:
    return judge(
        role=JUDGE_ROLE, rubric=JUDGE_RUBRIC, dimensions=dimensions, reference=reference, candidate=candidate,
        task="qa_draft", reference_label="REFERENCE (current draft + instruction)", candidate_label="CANDIDATE (final reply)",
    )


JUDGE_SMOKE: list[dict[str, Any]] = [
    {
        "name": "clean revise (shorter, numbers + escalation kept) scores high",
        "reference": "Draft: Hi Sara, mild swelling after 20u Botox is normal in the first days. If it worsens, contact the clinic. — Dr. Demo\nInstruction: make it a bit shorter and warmer.",
        "candidate": "Hi Sara, a little swelling after your 20u Botox is completely normal early on — if it worsens, just reach the clinic. — Dr. Demo",
        "expectHigh": True,
    },
    {
        "name": "revise that drops the escalation + alters the dose scores low",
        "reference": "Draft: Hi Sara, mild swelling after 20u Botox is normal. If it worsens, contact the clinic. — Dr. Demo\nInstruction: make it warmer.",
        "candidate": "Hi Sara, swelling after 30u Botox is totally fine, nothing to worry about at all. — Dr. Demo",
        "expectHigh": False,
    },
]


# --- Fixture-driven cases (real audio: r01–r10, recorded by the user) ------------------------------


def _fixture_payload(spec: dict[str, Any]) -> dict[str, Any]:
    qa = spec.get("qaRevise", {})
    return {
        "job": {"id": "eval-job", "jobType": "qa_revise"},
        "aiModels": {},
        "qaRevise": {
            "currentDraft": qa.get("currentDraft", ""),
            "patientQuestion": qa.get("patientQuestion", ""),
            "patientContext": qa.get("patientContext", {}),
            "priorAnswers": qa.get("priorAnswers", []),
            "doctorName": qa.get("doctorName", "دکتر دمو"),
        },
        # The eval passes audio bytes directly; a sentinel fallback flags an unusable gateway output.
        "deterministicFallback": {"mode": "revise", "reply": "FALLBACK_SENTINEL — do not score", "source": "mock-deterministic"},
    }


def run_fixture_cases() -> tuple[int, int, int, int, str | None]:
    fixtures = load_fixtures("qa_revise", AUDIO_SUFFIXES)
    if not fixtures:
        print("\n(no qa_revise clips staged — record r01–r10 per RECORDING_CHECKLIST.md; harness stays green)")
        return 0, 0, 0, 0, None
    print("\n--- qa_revise fixture cases (real voice notes → gateway) ---")
    safety_pass = safety_fail = quality_pass = quality_fail = 0
    prompt_version: str | None = None
    for fixture in fixtures:
        name = fixture["name"]
        spec = fixture.get("spec")
        if not spec:
            print(f"  SKIP {name}: missing/invalid .json spec")
            continue
        audio = fixture["media"].read_bytes()
        try:
            output = completed_qa_revise_output(_fixture_payload(spec), audio)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR {name}: job failed: {exc!r}")
            break
        if not str(output.get("source") or "").startswith("ai:"):
            print(f"  WARN {name}: output unusable; fell back — not scored")
            continue
        prompt_version = prompt_version or output.get("promptVersion")
        current_draft = spec.get("qaRevise", {}).get("currentDraft", "")
        problems = run_gates(output, current_draft, spec.get("expect", {}))
        if problems:
            safety_fail += 1
            print(f"  SAFETY FAIL {name}: {'; '.join(problems)}")
        else:
            safety_pass += 1
            print(f"  SAFETY PASS {name}  → mode={output.get('mode')} {str(output.get('reply'))[:60]!r}")
        judge_block = spec.get("judge")
        if judge_block:
            reference = f"Draft: {current_draft}\nInstruction: {spec.get('said', '(see clip)')}"
            try:
                result = judge_reply(reference, str(output.get("reply") or ""), list(JUDGE_DIMENSIONS))
            except Exception as exc:  # noqa: BLE001
                print(f"           QUALITY SKIP: judge unreachable: {exc!r}")
                continue
            if not result.get("ok"):
                print(f"           QUALITY WARN: {result.get('rationale')}")
                continue
            threshold = float(judge_block.get("minScore", DEFAULT_MIN_SCORE))
            if min_score(result["scores"]) >= threshold:
                quality_pass += 1
                print(f"           QUALITY PASS ({quality_line(result['scores'], threshold)})")
            else:
                quality_fail += 1
                print(f"           QUALITY FAIL ({quality_line(result['scores'], threshold)}) — {result.get('rationale')}")
    return safety_pass, safety_fail, quality_pass, quality_fail, prompt_version


def run_judge_smoke() -> bool:
    if not gateway_configured():
        return True
    print("\n--- judge smoke (does the rubric separate clean from botched?) ---")
    ok = True
    for index, case in enumerate(JUDGE_SMOKE, start=1):
        try:
            result = judge_reply(case["reference"], case["candidate"], list(JUDGE_DIMENSIONS))
        except Exception as exc:  # noqa: BLE001
            print(f"  [{index}] SKIP judge unreachable: {exc!r}")
            return True
        if not result.get("ok"):
            print(f"  [{index}] WARN judge non-JSON: {result.get('rationale')}")
            continue
        low = min_score(result["scores"])
        passed = (low >= DEFAULT_MIN_SCORE) if case["expectHigh"] else (low < DEFAULT_MIN_SCORE)
        ok = ok and passed
        print(f"  [{index}] {'OK  ' if passed else 'BUG '} {case['name']} → {quality_line(result['scores'], DEFAULT_MIN_SCORE)}")
    return ok


def main() -> int:
    models = env_models("AI_ENGINE_QA_DRAFT_MODEL", "AI_ENGINE_TRANSCRIPTION_MODEL")
    parser_ok = run_parser_self_tests()
    gates_ok = run_gate_self_tests()
    self_tests_ok = parser_ok and gates_ok
    if not gateway_configured():
        print("\nSKIP: no AI gateway configured. Fixture cases not run; self-tests above stand.")
        write_scorecard(
            "qa_revise_eval",
            metrics={"self_tests_ok": int(self_tests_ok), "safety_pass": 0, "safety_fail": 0,
                     "quality_pass": 0, "quality_fail": 0, "judge_smoke_ok": 1, "cases_total": 0},
            models_under_test=models,
        )
        return 0 if self_tests_ok else 1

    judge_smoke_ok = run_judge_smoke()
    safety_pass, safety_fail, quality_pass, quality_fail, prompt_version = run_fixture_cases()

    print(f"\n{'=' * 8} QA-REVISE SCORECARD {'=' * 8}")
    print(f"  self-tests:    {'PASS' if self_tests_ok else 'FAIL (harness bug)'}")
    print(f"  judge smoke:   {'PASS' if judge_smoke_ok else 'FAIL'}")
    print(f"  safety gates:  {safety_pass} pass / {safety_fail} fail")
    print(f"  quality (judge): {quality_pass} pass / {quality_fail} below threshold  "
          f"({'blocking' if STRICT_QUALITY else 'advisory'})")
    write_scorecard(
        "qa_revise_eval",
        metrics={"self_tests_ok": int(self_tests_ok), "safety_pass": safety_pass, "safety_fail": safety_fail,
                 "quality_pass": quality_pass, "quality_fail": quality_fail, "judge_smoke_ok": int(judge_smoke_ok),
                 "cases_total": safety_pass + safety_fail},
        models_under_test=models,
        prompt_version=prompt_version,
    )
    return exit_code(self_tests_ok=self_tests_ok, safety_fail=safety_fail, quality_fail=quality_fail, judge_smoke_ok=judge_smoke_ok)


if __name__ == "__main__":
    raise SystemExit(main())
