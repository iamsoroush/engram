import unittest
from unittest.mock import MagicMock, patch

from ai_engine.processing import completed_qa_draft_output, parse_qa_draft_output
from ai_engine.prompts.qa_draft import build as qa_draft_prompt

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


class QaDraftPromptGroundingTests(unittest.TestCase):
    """v2 retrieval grounding (AES-410): the exemplar block + guardrail rules render when present."""

    def test_no_exemplar_block_when_none_retrieved(self):
        prompt = qa_draft_prompt(PAYLOAD)
        self.assertNotIn("Retrieved exemplars", prompt)

    def test_exemplar_block_and_grounding_rules_render(self):
        payload = {
            "qaDraft": {
                **PAYLOAD["qaDraft"],
                "retrievedExemplars": [
                    {"question": "swelling after filler?", "answer": "mild swelling is normal", "source": "template"}
                ],
            }
        }
        prompt = qa_draft_prompt(payload)
        self.assertIn("Retrieved exemplars", prompt)
        self.assertIn("mild swelling is normal", prompt)
        # The three safety-priority rules must be present verbatim in spirit.
        self.assertIn("PATIENT'S CONTEXT always wins", prompt)
        self.assertIn("NEVER copy a specific dose", prompt)
        self.assertIn("escalate", prompt.lower())


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
