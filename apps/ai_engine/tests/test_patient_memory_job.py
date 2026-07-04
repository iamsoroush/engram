import unittest
from unittest.mock import MagicMock, patch

from ai_engine.processing import completed_patient_memory_output, parse_patient_memory_output

FALLBACK = {
    "summary": "Fallback summary.",
    "history": {"snapshot": "snap", "sections": [{"label": "Story so far", "body": "x"}], "visits": []},
    "source": "mock-deterministic",
}


def _response(text):
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = text
    return response


class ParsePatientMemoryTests(unittest.TestCase):
    def test_valid_json(self):
        out = parse_patient_memory_output(
            '{"summary":"S","history":{"snapshot":"snap","sections":[{"label":"L","body":"B"}],"visits":[]}}'
        )
        self.assertEqual(out["summary"], "S")
        self.assertEqual(out["history"]["snapshot"], "snap")

    def test_fenced_json_is_stripped(self):
        out = parse_patient_memory_output(
            '```json\n{"summary":"S","history":{"snapshot":"snap","sections":[{"label":"L","body":"B"}]}}\n```'
        )
        self.assertIsNotNone(out)
        self.assertEqual(out["summary"], "S")

    def test_invalid_returns_none(self):
        self.assertIsNone(parse_patient_memory_output("not json at all"))
        self.assertIsNone(parse_patient_memory_output(""))
        self.assertIsNone(parse_patient_memory_output('{"summary":"S"}'))  # no history
        self.assertIsNone(parse_patient_memory_output('{"summary":"S","history":{"snapshot":"x","sections":[]}}'))  # empty sections


class CompletedPatientMemoryTests(unittest.TestCase):
    def test_no_gateway_uses_fallback(self):
        with patch("ai_engine.jobs.patient_memory.transcription_is_configured", return_value=False):
            out = completed_patient_memory_output({"tier": "pro", "deterministicFallback": FALLBACK})
        self.assertEqual(out["summary"], "Fallback summary.")
        self.assertEqual(out["source"], "mock-deterministic")

    def test_gateway_ai_output(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _response(
            '{"summary":"AI sum","history":{"snapshot":"snap","sections":[{"label":"Story so far","body":"b"}],"visits":[]}}'
        )
        with patch("ai_engine.jobs.patient_memory.transcription_is_configured", return_value=True), patch(
            "ai_engine.jobs.patient_memory.gateway_client", return_value=client
        ), patch("ai_engine.jobs.patient_memory.resolve_model", return_value="test-model"):
            out = completed_patient_memory_output(
                {"tier": "pro", "deterministicFallback": FALLBACK, "patient": {"displayName": "X"}, "aiModels": {}}
            )
        self.assertEqual(out["summary"], "AI sum")
        self.assertEqual(out["source"], "ai:test-model")
        self.assertEqual(out["model"], "test-model")
        self.assertEqual(out["history"]["source"], "ai:test-model")

    def test_gateway_bad_output_falls_back(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _response("garbage, not json")
        with patch("ai_engine.jobs.patient_memory.transcription_is_configured", return_value=True), patch(
            "ai_engine.jobs.patient_memory.gateway_client", return_value=client
        ), patch("ai_engine.jobs.patient_memory.resolve_model", return_value="test-model"):
            out = completed_patient_memory_output(
                {"tier": "pro", "deterministicFallback": FALLBACK, "patient": {}, "aiModels": {}}
            )
        self.assertEqual(out["source"], "mock-deterministic")
        self.assertEqual(out["summary"], "Fallback summary.")


if __name__ == "__main__":
    unittest.main()
