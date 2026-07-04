"""Typed-contract parity gate (Axis-1 increment 3).

Proves the new pydantic-model-backed parsers reproduce the OLD dict-shaping parsers byte-for-byte —
including on malformed inputs — so the swap does not silently tighten (or loosen) tolerance. The
``old`` side is ``tests/contract_goldens.json``, captured from the parsers at the increment's branch
point (see ``scripts/capture_goldens`` in the increment commit). The ``new`` side is the current
``contracts.*`` parsers. Volatile timestamps are stripped from both; raised exceptions are pinned as a
``{"__raises__": "<Type>: <message>"}`` sentinel (the transcription parser raises on malformed input).

Regenerating the goldens is a deliberate act: if a golden changes, that IS a behavior change and must
be justified, not rubber-stamped.
"""
import json
import pathlib
import unittest

from tests.contract_corpus import (
    CAPTION_CASES,
    INTENTS_CASES,
    MEMORY_CASES,
    QA_DRAFT_CASES,
    QA_REVISE_CASES,
    SAFETY_RECONCILE_CASES,
    SAFETY_RECONCILE_KEYS,
    SYNTHESIS_CASES,
    TRANSCRIPTION_CASES,
)
from ai_engine.contracts.caption import parse_caption_output
from ai_engine.contracts.capture import normalize_intents, parse_structured_transcription_output
from ai_engine.contracts.memory import parse_patient_memory_output
from ai_engine.contracts.qa import parse_qa_draft_output, parse_qa_revise_output
from ai_engine.contracts.safety_reconcile import parse_safety_reconcile_output
from ai_engine.contracts.synthesis import parse_session_synthesis_output

GOLDENS = json.loads((pathlib.Path(__file__).parent / "contract_goldens.json").read_text(encoding="utf-8"))
VOLATILE_KEYS = {"generated_at", "generatedAt"}


def _strip_volatile(value):
    if isinstance(value, dict):
        return {k: _strip_volatile(v) for k, v in value.items() if k not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [_strip_volatile(v) for v in value]
    return value


def _capture(fn, *args, **kwargs):
    """Run a parser, returning its stripped output or a ``{__raises__}`` sentinel — mirrors capture.

    RuntimeError subclasses canonicalize to ``RuntimeError`` so the §3.6 exception refinement
    (RuntimeError → InvalidOutput, same message, still a RuntimeError) reads as behavior-preserving at
    the parse-contract level — the invariant is "raises a retryable RuntimeError with this message".
    """
    try:
        return _strip_volatile(fn(*args, **kwargs))
    except Exception as exc:  # noqa: BLE001 — parity pins raise-behavior too
        name = "RuntimeError" if isinstance(exc, RuntimeError) else type(exc).__name__
        return {"__raises__": f"{name}: {exc}"}


class ContractParityTests(unittest.TestCase):
    def _assert_family(self, family, cases, fn, arg_fn=None):
        goldens = GOLDENS[family]
        self.assertEqual(len(goldens), len(cases), f"{family}: corpus/golden count drift")
        for label, raw in cases:
            with self.subTest(family=family, case=label):
                actual = _capture(fn, *(arg_fn(raw) if arg_fn else (raw,)))
                self.assertEqual(actual, goldens[label], f"{family}.{label} diverged from the frozen parser")

    def test_transcription_parity(self):
        self._assert_family("transcription", TRANSCRIPTION_CASES, parse_structured_transcription_output)

    def test_intents_parity(self):
        self._assert_family("intents", INTENTS_CASES, normalize_intents)

    def test_caption_parity(self):
        self._assert_family("caption", CAPTION_CASES, parse_caption_output)

    def test_memory_parity(self):
        self._assert_family("memory", MEMORY_CASES, parse_patient_memory_output)

    def test_qa_draft_parity(self):
        self._assert_family("qa_draft", QA_DRAFT_CASES, parse_qa_draft_output)

    def test_qa_revise_parity(self):
        self._assert_family("qa_revise", QA_REVISE_CASES, parse_qa_revise_output)

    def test_safety_reconcile_parity(self):
        goldens = GOLDENS["safety_reconcile"]
        self.assertEqual(len(goldens), len(SAFETY_RECONCILE_CASES))
        for label, raw in SAFETY_RECONCILE_CASES:
            with self.subTest(case=label):
                actual = _capture(parse_safety_reconcile_output, raw, candidate_keys=SAFETY_RECONCILE_KEYS)
                self.assertEqual(actual, goldens[label], f"safety_reconcile.{label} diverged")

    def test_synthesis_parity(self):
        goldens = GOLDENS["synthesis"]
        self.assertEqual(len(goldens), len(SYNTHESIS_CASES))
        for label, raw, ids, lang in SYNTHESIS_CASES:
            with self.subTest(case=label):
                actual = _capture(parse_session_synthesis_output, raw, source_capture_ids=ids, report_language=lang)
                self.assertEqual(actual, goldens[label], f"synthesis.{label} diverged")


if __name__ == "__main__":
    unittest.main()
