import unittest
from unittest.mock import MagicMock, patch

from ai_engine import processing
from ai_engine.processing import (
    caption_prompt,
    decorate_note_content,
    caption_image_content,
    enrichment_language_directive,
    image_to_data_url,
    is_fixture_capture,
    note_decoration_prompt,
    raw_note_text_for_decoration,
    run_capture_processing_job,
)


def _gateway_response(text):
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = text
    return response


class EnrichmentPromptTests(unittest.TestCase):
    def test_language_directive_auto_preserves_script(self):
        directive = enrichment_language_directive({"preferredLanguage": "auto"})
        self.assertIn("same language and script", directive)
        self.assertIn("never romanize", directive.lower())

    def test_language_directive_specific_names_native_script(self):
        directive = enrichment_language_directive({"preferredLanguage": "fa"})
        self.assertIn("Persian (Farsi)", directive)
        self.assertIn("native script", directive)

    def test_caption_prompt_has_aesthetics_context_and_no_invention(self):
        prompt = caption_prompt({"clinic": {"name": "Memora Clinic"}, "preferredLanguage": "auto"})
        self.assertIn("aesthetics clinic", prompt.lower())
        self.assertIn("Do NOT invent", prompt)
        self.assertIn("Memora Clinic", prompt)
        self.assertIn("never romanize", prompt.lower())

    def test_note_decoration_prompt_preserves_details(self):
        prompt = note_decoration_prompt({"preferredLanguage": "fa"})
        self.assertIn("Preserve EVERY clinical detail", prompt)
        self.assertIn("do NOT add facts", prompt)
        self.assertIn("Persian (Farsi)", prompt)


class EnrichmentHelperTests(unittest.TestCase):
    def test_image_to_data_url_uses_image_mime(self):
        url = image_to_data_url(b"\x89PNG", "image/png")
        self.assertTrue(url.startswith("data:image/png;base64,"))

    def test_image_to_data_url_defaults_non_image_mime_to_jpeg(self):
        url = image_to_data_url(b"x", "application/octet-stream")
        self.assertTrue(url.startswith("data:image/jpeg;base64,"))

    def test_is_fixture_capture_by_filename_and_detail(self):
        self.assertTrue(is_fixture_capture({"metadata": {"original_filename": "photo_01_pre_correction_left_cheek.jpg"}}))
        self.assertTrue(
            is_fixture_capture(
                {
                    "metadata": {
                        "detail": "Patient prefers subtle correction ... send a follow-up photo in 2 weeks if asymmetry persists."
                    }
                }
            )
        )
        self.assertFalse(is_fixture_capture({"metadata": {"detail": "Botox to forehead, 20 units."}}))

    def test_raw_note_text_for_decoration(self):
        self.assertEqual(raw_note_text_for_decoration({"metadata": {"detail": "  note  "}}), "note")
        self.assertIsNone(raw_note_text_for_decoration({"metadata": {"detail": "   "}}))
        self.assertIsNone(raw_note_text_for_decoration({"metadata": {}}))


class EnrichmentGatewayTests(unittest.TestCase):
    @patch("ai_engine.processing.gateway_client")
    def test_caption_returns_text(self, client_factory):
        client_factory.return_value.chat.completions.create.return_value = _gateway_response(
            "Pre-correction image of mild left cheek asymmetry."
        )
        caption = caption_image_content(b"img", "image/jpeg", {"preferredLanguage": "auto"})
        self.assertEqual(caption, "Pre-correction image of mild left cheek asymmetry.")

    @patch("ai_engine.processing.gateway_client")
    def test_caption_empty_response_is_none(self, client_factory):
        client_factory.return_value.chat.completions.create.return_value = _gateway_response("  ")
        self.assertIsNone(caption_image_content(b"img", "image/jpeg", None))

    @patch("ai_engine.processing.gateway_client")
    def test_decorate_note_returns_text(self, client_factory):
        client_factory.return_value.chat.completions.create.return_value = _gateway_response("Decorated note.")
        self.assertEqual(decorate_note_content("raw note", {"preferredLanguage": "fa"}), "Decorated note.")


class FakeBackendClient:
    """Minimal BackendClient stand-in capturing the completed output."""

    def __init__(self, payload):
        self._payload = payload
        self.completed = None
        self.progressed = []
        self.files = {}

    def start_job(self, job_id, *, celery_task_id, retry_count):
        return self._payload

    def progress_job(self, job_id, *, output_key, output, stage):
        self.progressed.append((output_key, stage))

    def get_file(self, path):
        return self.files.get(path, (b"img-bytes", "image/jpeg"))

    def complete_job(self, job_id, *, output_key, output):
        self.completed = (output_key, output)


class RunCaptureEnrichmentTests(unittest.TestCase):
    def _payload(self, capture_type, *, enrichment=True, metadata=None):
        return {
            "job": {"id": "job-1", "jobType": f"{capture_type}_capture_process", "inputArtifactIds": ["a-1"]},
            "capture": {
                "id": "cap-1",
                "type": capture_type,
                "status": "processing",
                "metadata": metadata or {},
                "sourceArtifactId": "art-1",
            },
            "transcriptionContext": None,
            "enrichmentContext": {"preferredLanguage": "auto"} if enrichment else None,
        }

    @patch("ai_engine.processing.transcription_is_configured", return_value=True)
    @patch("ai_engine.processing.caption_image_content", return_value="A clinical caption.")
    def test_pro_photo_is_captioned(self, _caption, _configured):
        fake = FakeBackendClient(self._payload("photo"))
        with patch("ai_engine.processing.BackendClient", return_value=fake):
            run_capture_processing_job("job-1", celery_task_id=None, retry_count=0)
        self.assertEqual(fake.completed[0], "caption")
        self.assertEqual(fake.completed[1]["text"], "A clinical caption.")

    @patch("ai_engine.processing.transcription_is_configured", return_value=True)
    @patch("ai_engine.processing.decorate_note_content", return_value="Decorated.")
    def test_pro_note_is_decorated(self, _decorate, _configured):
        fake = FakeBackendClient(self._payload("note", metadata={"detail": "raw note text"}))
        with patch("ai_engine.processing.BackendClient", return_value=fake):
            run_capture_processing_job("job-1", celery_task_id=None, retry_count=0)
        self.assertEqual(fake.completed[0], "decorated_text")
        self.assertEqual(fake.completed[1]["text"], "Decorated.")

    @patch("ai_engine.processing.transcription_is_configured", return_value=True)
    @patch("ai_engine.processing.caption_image_content", return_value="ignored")
    def test_basic_photo_has_no_caption(self, caption, _configured):
        # No enrichmentContext (Basic tenant) → never calls the gateway and writes NO caption
        # (blank), so the UI offers a manual "Add caption" instead of a placeholder.
        fake = FakeBackendClient(self._payload("photo", enrichment=False))
        with patch("ai_engine.processing.BackendClient", return_value=fake):
            run_capture_processing_job("job-1", celery_task_id=None, retry_count=0)
        caption.assert_not_called()
        self.assertEqual(fake.completed[0], "caption")
        self.assertEqual(fake.completed[1]["text"], "")

    @patch("ai_engine.processing.transcription_is_configured", return_value=True)
    @patch("ai_engine.processing.caption_image_content", return_value=None)
    def test_empty_caption_yields_no_caption(self, _caption, _configured):
        # An empty gateway response leaves the photo without a caption (manual add), not a placeholder.
        fake = FakeBackendClient(self._payload("photo"))
        with patch("ai_engine.processing.BackendClient", return_value=fake):
            run_capture_processing_job("job-1", celery_task_id=None, retry_count=0)
        self.assertEqual(fake.completed[0], "caption")
        self.assertEqual(fake.completed[1]["text"], "")

    @patch("ai_engine.processing.transcription_is_configured", return_value=True)
    @patch("ai_engine.processing.caption_image_content", return_value="ignored")
    def test_fixture_photo_skips_enrichment(self, caption, _configured):
        payload = self._payload("photo", metadata={"original_filename": "photo_01_pre_correction_left_cheek.jpg"})
        fake = FakeBackendClient(payload)
        with patch("ai_engine.processing.BackendClient", return_value=fake):
            run_capture_processing_job("job-1", celery_task_id=None, retry_count=0)
        caption.assert_not_called()
        self.assertEqual(
            fake.completed[1]["text"],
            processing.TEST_CAPTURE_TEXT_BY_FILENAME["photo_01_pre_correction_left_cheek.jpg"],
        )


if __name__ == "__main__":
    unittest.main()
