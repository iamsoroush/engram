"""Characterization tests pinning the thin, pure parser/helper seams the package split leans on.

These lock the CURRENT behavior of small pure functions that were only thinly (or indirectly)
covered, so the Axis-1 refactor that moves them into ``core/`` and ``jobs/`` cannot drift them. No
new behavior is asserted — every expectation mirrors the code as it stands before the split.
"""
import unittest

from ai_engine.processing import (
    clamp_confidence,
    is_expected_test_fixture,
    first_capture_by_text,
    normalize_intents,
    output_key_for_capture,
    parse_qa_revise_output,
    parse_safety_reconcile_output,
    session_synthesis_skip_output,
    _safety_flag_key,
)


class ParseQaReviseTests(unittest.TestCase):
    def test_valid_json_returns_mode_and_reply(self):
        out = parse_qa_revise_output('{"mode":"replace","reply":"Hello there."}')
        self.assertEqual(out, {"mode": "replace", "reply": "Hello there."})

    def test_fenced_json_is_stripped(self):
        out = parse_qa_revise_output('```json\n{"mode":"revise","reply":"Trimmed."}\n```')
        self.assertEqual(out, {"mode": "revise", "reply": "Trimmed."})

    def test_unknown_mode_defaults_to_revise(self):
        out = parse_qa_revise_output('{"mode":"weird","reply":"R"}')
        self.assertEqual(out["mode"], "revise")

    def test_missing_mode_defaults_to_revise(self):
        out = parse_qa_revise_output('{"reply":"R"}')
        self.assertEqual(out["mode"], "revise")

    def test_empty_or_missing_reply_is_none(self):
        self.assertIsNone(parse_qa_revise_output(""))
        self.assertIsNone(parse_qa_revise_output("   "))
        self.assertIsNone(parse_qa_revise_output("not json"))
        self.assertIsNone(parse_qa_revise_output('{"mode":"revise"}'))
        self.assertIsNone(parse_qa_revise_output('{"mode":"revise","reply":"  "}'))
        self.assertIsNone(parse_qa_revise_output('["not","an","object"]'))


class ParseSafetyReconcileTests(unittest.TestCase):
    KEYS = ["allergy|penicillin", "allergy|penicillin sensitivity", "consent|signed"]

    def test_keep_duplicate_superseded_decisions(self):
        raw = (
            '{"decisions":['
            '{"key":"allergy|penicillin","status":"keep"},'
            '{"key":"allergy|penicillin sensitivity","status":"duplicate","ofKey":"allergy|penicillin"},'
            '{"key":"consent|signed","status":"superseded","ofKey":"allergy|penicillin"}]}'
        )
        out = parse_safety_reconcile_output(raw, candidate_keys=self.KEYS)
        self.assertEqual(out["allergy|penicillin"], {"status": "keep", "ofKey": None})
        self.assertEqual(
            out["allergy|penicillin sensitivity"], {"status": "duplicate", "ofKey": "allergy|penicillin"}
        )
        self.assertEqual(out["consent|signed"], {"status": "superseded", "ofKey": "allergy|penicillin"})

    def test_unknown_key_is_dropped(self):
        raw = '{"decisions":[{"key":"not|a|candidate","status":"keep"}]}'
        out = parse_safety_reconcile_output(raw, candidate_keys=self.KEYS)
        self.assertEqual(out, {})

    def test_ofkey_not_a_candidate_downgrades_to_keep(self):
        raw = '{"decisions":[{"key":"allergy|penicillin","status":"duplicate","ofKey":"ghost|key"}]}'
        out = parse_safety_reconcile_output(raw, candidate_keys=self.KEYS)
        self.assertEqual(out["allergy|penicillin"], {"status": "keep", "ofKey": None})

    def test_ofkey_equal_to_key_downgrades_to_keep(self):
        raw = '{"decisions":[{"key":"allergy|penicillin","status":"duplicate","ofKey":"allergy|penicillin"}]}'
        out = parse_safety_reconcile_output(raw, candidate_keys=self.KEYS)
        self.assertEqual(out["allergy|penicillin"], {"status": "keep", "ofKey": None})

    def test_empty_or_malformed_returns_none(self):
        self.assertIsNone(parse_safety_reconcile_output("", candidate_keys=self.KEYS))
        self.assertIsNone(parse_safety_reconcile_output("   ", candidate_keys=self.KEYS))
        self.assertIsNone(parse_safety_reconcile_output("not json", candidate_keys=self.KEYS))
        self.assertIsNone(parse_safety_reconcile_output('{"nope":1}', candidate_keys=self.KEYS))

    def test_safety_flag_key_is_normalized(self):
        self.assertEqual(_safety_flag_key("allergy", "  Penicillin   Allergy "), "allergy|penicillin allergy")


class NormalizeIntentsTests(unittest.TestCase):
    def test_non_dict_is_none(self):
        self.assertIsNone(normalize_intents("x"))
        self.assertIsNone(normalize_intents(None))

    def test_empty_dict_is_none(self):
        self.assertIsNone(normalize_intents({}))

    def test_absent_present_false_intents_dropped(self):
        self.assertIsNone(normalize_intents({"assignment": {"present": False}, "append": {"present": False}}))

    def test_append_and_out_of_context(self):
        out = normalize_intents(
            {
                "append": {"present": True, "confidence": 0.4},
                "out_of_context": {"present": True, "confidence": 2, "reason": " not clinical "},
            }
        )
        self.assertEqual(out["append"], {"present": True, "confidence": 0.4})
        self.assertEqual(out["out_of_context"], {"present": True, "confidence": 1.0, "reason": "not clinical"})
        self.assertNotIn("assignment", out)


class MiscSeamTests(unittest.TestCase):
    def test_session_synthesis_skip_output_shape(self):
        out = session_synthesis_skip_output("gateway_not_configured")
        self.assertTrue(out["synthesis_skipped"])
        self.assertEqual(out["status"], "skipped")
        self.assertEqual(out["reason"], "gateway_not_configured")
        self.assertEqual(out["generated_by"], "ai-engine")
        self.assertIn("generated_at", out)

    def test_output_key_for_capture(self):
        self.assertEqual(output_key_for_capture("audio"), "transcript")
        self.assertEqual(output_key_for_capture("photo"), "caption")
        self.assertEqual(output_key_for_capture("note"), "note_text")
        self.assertEqual(output_key_for_capture("anything-else"), "note_text")

    def test_clamp_confidence(self):
        self.assertEqual(clamp_confidence(0.5), 0.5)
        self.assertEqual(clamp_confidence(5), 1.0)
        self.assertEqual(clamp_confidence(-1), 0.0)
        self.assertEqual(clamp_confidence("x"), 0.0)
        self.assertEqual(clamp_confidence(None), 0.0)

    def test_is_expected_test_fixture_and_first_capture_by_text(self):
        captures = [
            {"type": "audio", "transcript": "Follow-up after cheek filler; mild asymmetry on the left cheek."},
            {"type": "audio", "transcript": "Injected 0.3 mL hyaluronic acid filler; avoid heavy exercise for 24 hours."},
        ]
        self.assertTrue(is_expected_test_fixture(captures))
        self.assertFalse(is_expected_test_fixture([{"type": "note", "rawText": "unrelated"}]))
        found = first_capture_by_text(captures, "hyaluronic acid")
        self.assertIs(found, captures[1])
        self.assertIsNone(first_capture_by_text(captures, "no such text"))


if __name__ == "__main__":
    unittest.main()
