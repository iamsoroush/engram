import unittest
from unittest.mock import MagicMock, patch

from ai_engine.processing import completed_qa_draft_output, parse_qa_draft_output

PAYLOAD = {
    "qaDraft": {
        "patientQuestion": "Can I exercise tomorrow?",
        "patientContext": {"displayName": "Sara N.", "recentVisitSummaries": ["Forehead Botox 20u."]},
        "priorAnswers": [{"question": "swelling?", "answer": "usually settles in a day or two"}],
        "doctorName": "Dr. Demo",
        "clinicName": "Engram Demo Clinic",
    },
    "deterministicFallback": {"draft": "Hi Sara, please rest for 24 hours. — Dr. Demo", "source": "mock-deterministic"},
    "aiModels": {},
}


def _response(text):
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = text
    return response


class ParseQaDraftTests(unittest.TestCase):
    def test_plain_text(self):
        self.assertEqual(parse_qa_draft_output("Hi Sara, rest up.  "), "Hi Sara, rest up.")

    def test_strips_code_fence(self):
        self.assertEqual(parse_qa_draft_output("```\nHi Sara, rest up.\n```"), "Hi Sara, rest up.")

    def test_empty_is_none(self):
        self.assertIsNone(parse_qa_draft_output("   "))


class CompletedQaDraftTests(unittest.TestCase):
    def test_no_gateway_uses_fallback(self):
        with patch("ai_engine.jobs.qa_draft.transcription_is_configured", return_value=False):
            out = completed_qa_draft_output(PAYLOAD)
        self.assertEqual(out["draft"], "Hi Sara, please rest for 24 hours. — Dr. Demo")
        self.assertEqual(out["source"], "mock-deterministic")

    def test_gateway_ai_output(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _response("Hi Sara, hold off on the gym for a day. — Dr. Demo")
        with patch("ai_engine.jobs.qa_draft.transcription_is_configured", return_value=True), patch(
            "ai_engine.jobs.qa_draft.gateway_client", return_value=client
        ), patch("ai_engine.jobs.qa_draft.resolve_model", return_value="test-model"):
            out = completed_qa_draft_output(PAYLOAD)
        self.assertEqual(out["draft"], "Hi Sara, hold off on the gym for a day. — Dr. Demo")
        self.assertEqual(out["source"], "ai:test-model")

    def test_unusable_gateway_output_falls_back(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _response("   ")
        with patch("ai_engine.jobs.qa_draft.transcription_is_configured", return_value=True), patch(
            "ai_engine.jobs.qa_draft.gateway_client", return_value=client
        ), patch("ai_engine.jobs.qa_draft.resolve_model", return_value="test-model"):
            out = completed_qa_draft_output(PAYLOAD)
        self.assertEqual(out["source"], "mock-deterministic")


if __name__ == "__main__":
    unittest.main()
