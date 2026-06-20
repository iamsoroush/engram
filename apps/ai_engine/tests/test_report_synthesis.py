import json
import unittest
from unittest.mock import MagicMock, patch

from ai_engine.processing import (
    SESSION_SYNTHESIS_OUTPUT_VERSION,
    SYNTHESIS_SECTION_IDS,
    completed_session_synthesis_output,
    parse_session_synthesis_output,
    report_synthesis_prompt,
    resolve_model,
    resolve_reasoning_effort,
)


def _response(text):
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = text
    return response


CANNED_SYNTHESIS = json.dumps(
    {
        "summary": "Follow-up gel touch-up on the left cheek.",
        "language": "fa",
        "sections": [
            {"id": "visit-summary", "title": "Visit summary", "blocks": [{"type": "paragraph", "text": "بیمار برای ترمیم آمد."}]},
            {"id": "treatment-performed", "title": "Treatment performed", "blocks": [{"type": "paragraph", "text": "ژل ۳ سی‌سی"}]},
            {"id": "media", "title": "Media", "blocks": [{"type": "image", "captureId": "cap-a", "caption": "photo"}]},
        ],
        "treatments": [
            {
                "area": "left cheek",
                "product": "gel",
                "brand": "Juvederm",
                "quantity": 3,
                "unit": "cc",
                "quantityText": "۳ سی‌سی",
                "lot": None,
                "confidence": 0.9,
                "sourceCaptureIds": ["cap-a"],
                "evidence": "spoken",
                "carriedForward": False,
                "supersedesCaptureId": None,
                "attributes": {"needleGauge": "27G"},
            }
        ],
        "uncertainties": [],
    },
    ensure_ascii=False,
)


class ParseSynthesisTests(unittest.TestCase):
    def test_parses_and_fills_all_fixed_sections(self):
        output = parse_session_synthesis_output(CANNED_SYNTHESIS, source_capture_ids=["cap-a", "cap-b"])
        self.assertIsNotNone(output)
        self.assertEqual(output["schemaVersion"], SESSION_SYNTHESIS_OUTPUT_VERSION)
        # All fixed section ids are present, in order, even those the model omitted.
        self.assertEqual([section["id"] for section in output["sections"]], list(SYNTHESIS_SECTION_IDS))
        self.assertEqual(output["language"], "fa")
        self.assertEqual(len(output["treatments"]), 1)
        self.assertEqual(output["treatments"][0]["quantityText"], "۳ سی‌سی")  # verbatim native script
        # sourceReferences cover every reportable capture so the backend can mark contributions.
        self.assertEqual(
            output["sourceReferences"],
            [{"type": "capture", "captureId": "cap-a"}, {"type": "capture", "captureId": "cap-b"}],
        )

    def test_fenced_json_is_stripped(self):
        output = parse_session_synthesis_output("```json\n" + CANNED_SYNTHESIS + "\n```", source_capture_ids=[])
        self.assertIsNotNone(output)
        self.assertEqual(output["summary"], "Follow-up gel touch-up on the left cheek.")

    def test_malformed_returns_none(self):
        self.assertIsNone(parse_session_synthesis_output("not json", source_capture_ids=[]))
        self.assertIsNone(parse_session_synthesis_output("", source_capture_ids=[]))
        self.assertIsNone(parse_session_synthesis_output('{"language":"fa"}', source_capture_ids=[]))  # no summary


class CompletedSynthesisOutputTests(unittest.TestCase):
    def _payload(self):
        return {
            "job": {"id": "job-1", "jobType": "session_organize"},
            "session": {"reportTemplateKey": "default"},
            "reportTemplate": {"key": "default"},
            "aiModels": {},
            "sessionProcessingContext": {
                "captures": {"audio": [{"captureId": "cap-a", "type": "audio", "transcript": "ژل ۳ سی‌سی"}], "photos": [], "text": []},
            },
        }

    def test_no_gateway_skips(self):
        with patch("ai_engine.processing.transcription_is_configured", return_value=False):
            output = completed_session_synthesis_output(self._payload())
        self.assertTrue(output["synthesis_skipped"])
        self.assertEqual(output["reason"], "gateway_not_configured")

    def test_malformed_gateway_output_skips(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _response("garbage, not json")
        with patch("ai_engine.processing.transcription_is_configured", return_value=True), patch(
            "ai_engine.processing.gateway_client", return_value=client
        ), patch("ai_engine.processing.resolve_model", return_value="m"):
            output = completed_session_synthesis_output(self._payload())
        self.assertTrue(output["synthesis_skipped"])
        self.assertEqual(output["reason"], "empty_or_malformed_synthesis")

    def test_gateway_synthesis_completes(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _response(CANNED_SYNTHESIS)
        with patch("ai_engine.processing.transcription_is_configured", return_value=True), patch(
            "ai_engine.processing.gateway_client", return_value=client
        ), patch("ai_engine.processing.resolve_model", return_value="m"):
            output = completed_session_synthesis_output(self._payload())
        self.assertEqual(output["status"], "completed")
        self.assertEqual(output["structured_report"]["schemaVersion"], SESSION_SYNTHESIS_OUTPUT_VERSION)
        self.assertEqual(output["extracted_metadata"]["treatments"][0]["product"], "gel")
        self.assertEqual(output["extracted_metadata"]["source_capture_ids"], ["cap-a"])
        # No temperature is ever sent; reasoning_effort rides extra_body.
        _, kwargs = client.chat.completions.create.call_args
        self.assertNotIn("temperature", kwargs)
        self.assertIn("response_format", kwargs)


class ConfigResolutionTests(unittest.TestCase):
    def test_resolve_model_accepts_string_and_object(self):
        self.assertEqual(resolve_model("report_synthesis", {"report_synthesis": "model-x"}), "model-x")
        self.assertEqual(resolve_model("report_synthesis", {"report_synthesis": {"model": "model-y", "reasoningEffort": "high"}}), "model-y")

    def test_resolve_reasoning_effort(self):
        self.assertEqual(
            resolve_reasoning_effort("report_synthesis", {"report_synthesis": {"model": "m", "reasoningEffort": "high"}}),
            "high",
        )
        # A bare model string carries no effort → fall back to the default.
        self.assertEqual(resolve_reasoning_effort("report_synthesis", {"report_synthesis": "m"}, default="low"), "low")
        self.assertIsNone(resolve_reasoning_effort("report_synthesis", {}, default=None))


class PromptTests(unittest.TestCase):
    def test_prompt_is_vertical_aware_and_demands_native_script(self):
        prompt = report_synthesis_prompt({"domain": {"label": "aesthetics clinic"}, "reportLanguage": "fa"})
        self.assertIn("aesthetics clinic", prompt)
        self.assertIn("fa", prompt)
        self.assertIn("supersedesCaptureId", prompt)
        self.assertIn("carriedForward", prompt)

    def test_prompt_neutral_clinic_when_no_domain(self):
        prompt = report_synthesis_prompt({})
        self.assertIn("clinic", prompt)


if __name__ == "__main__":
    unittest.main()
