import unittest
from unittest.mock import patch

from ai_engine.processing import (
    audio_to_flac_mono_16khz_base64,
    completed_audio_metadata,
    parse_structured_transcription_output,
    placeholder_text_for_capture,
    transcription_language_directive,
    transcription_prompt,
)


class TranscriptionLanguageDirectiveTests(unittest.TestCase):
    def test_auto_forbids_translation_and_romanization(self):
        directive = transcription_language_directive({"preferredLanguage": "auto"})
        self.assertIn("ORIGINAL SCRIPT", directive)
        self.assertIn("never romanize", directive.lower())

    def test_missing_or_blank_defaults_to_auto(self):
        self.assertIn("ORIGINAL SCRIPT", transcription_language_directive(None))
        self.assertIn("ORIGINAL SCRIPT", transcription_language_directive({"preferredLanguage": ""}))

    def test_specific_language_names_it_and_native_script(self):
        directive = transcription_language_directive({"preferredLanguage": "fa"})
        self.assertIn("Persian (Farsi)", directive)
        self.assertIn("native script", directive)

    def test_prompt_embeds_directive(self):
        self.assertIn("ORIGINAL SCRIPT", transcription_prompt(None))
        self.assertIn("Persian (Farsi)", transcription_prompt({"preferredLanguage": "fa"}))


class StructuredTranscriptionTests(unittest.TestCase):
    def test_parse_valid_structured_transcription(self):
        parsed = parse_structured_transcription_output(
            """
            {
              "transcript": "سلام Sara Nazari for cheek filler follow-up.",
              "language": "mixed",
              "patient_information": {
                "raw_mentioned_name": "سارا نظری",
                "standardized_display_name": "Sara Nazari",
                "alternate_transliterations": ["Sara Nazari", "Saraa Nazari"],
                "national_id": "0012345678",
                "phone": "09121234567",
                "date_of_birth": null,
                "evidence": "Name and national ID spoken in audio.",
                "confidence": 0.82
              },
              "clinical_summary": "Cheek filler follow-up.",
              "uncertainties": ["Date of birth not mentioned."]
            }
            """
        )

        self.assertEqual(parsed["transcript"], "سلام Sara Nazari for cheek filler follow-up.")
        self.assertEqual(parsed["language"], "mixed")
        self.assertEqual(parsed["patient_information"]["standardized_display_name"], "Sara Nazari")
        self.assertEqual(parsed["patient_information"]["national_id"], "0012345678")
        self.assertEqual(parsed["clinical_summary"], "Cheek filler follow-up.")
        self.assertEqual(parsed["uncertainties"], ["Date of birth not mentioned."])

    def test_malformed_structured_transcription_raises_retryable_error(self):
        with self.assertRaisesRegex(RuntimeError, "Audio transcription returned malformed structured JSON"):
            parse_structured_transcription_output("transcript: not json")

    def test_missing_ffmpeg_raises_conversion_failure(self):
        with patch("ai_engine.processing.subprocess.run", side_effect=FileNotFoundError("ffmpeg")):
            with self.assertRaisesRegex(RuntimeError, "Audio conversion to FLAC failed: ffmpeg"):
                audio_to_flac_mono_16khz_base64(b"audio")

    def test_prompt_includes_context_and_iranian_clinic_guidance(self):
        prompt = transcription_prompt(
            {
                "clinic": {"name": "Memora Clinic"},
                "assignedPatient": {"displayName": "Sara N."},
                "previousTranscripts": [{"text": "Previous cheek filler note."}],
                "textNotes": [{"text": "Prefers subtle correction."}],
            }
        )

        self.assertIn("Persian/Farsi", prompt)
        self.assertIn("Iranian national IDs", prompt)
        self.assertIn("Memora Clinic", prompt)
        self.assertIn("Previous cheek filler note.", prompt)
        self.assertIn("Prefers subtle correction.", prompt)

    def test_fixture_audio_output_is_structured_and_deterministic(self):
        output = completed_audio_metadata(
            {"id": "job-1", "jobType": "audio_capture_process", "inputArtifactIds": ["artifact-1"]},
            {
                "type": "audio",
                "metadata": {"original_filename": "audio_01_initial_consultation.wav"},
            },
            content=None,
        )

        self.assertEqual(output["status"], "completed")
        self.assertIn("Patient Sara Nazari", output["text"])
        self.assertIn("patient_information", output)
        self.assertEqual(output["patient_information"]["confidence"], 0.0)
        self.assertEqual(output["detected_patient"]["status"], "not_detected")

    def test_non_fixture_audio_requires_configured_transcription_gateway(self):
        with self.assertRaisesRegex(RuntimeError, "Audio transcription gateway is not configured"):
            completed_audio_metadata(
                {"id": "job-1", "jobType": "audio_capture_process", "inputArtifactIds": ["artifact-1"]},
                {
                    "type": "audio",
                    "metadata": {"original_filename": "clinic-audio.wav"},
                },
                content=None,
            )

    def test_placeholder_helper_does_not_generate_non_fixture_audio_text(self):
        with self.assertRaisesRegex(RuntimeError, "Audio transcription gateway is not configured"):
            placeholder_text_for_capture({"type": "audio", "metadata": {"detail": "Audio note saved."}})

    def test_parse_extracts_explicit_assignment_intent(self):
        parsed = parse_structured_transcription_output(
            """
            {
              "transcript": "نام بیمار عوض شه به سروش معاصد.",
              "language": "fa",
              "patient_information": {"raw_mentioned_name": "سروش معاصد", "confidence": 0.7},
              "clinical_summary": null,
              "uncertainties": [],
              "intents": {
                "assignment": {"present": true, "basis": "explicit", "confidence": 0.9, "evidence": "change the patient to Soroush"},
                "append": {"present": false, "confidence": 0.0},
                "out_of_context": {"present": false, "confidence": 0.0, "reason": null}
              }
            }
            """
        )

        self.assertIsNotNone(parsed["intents"])
        self.assertEqual(parsed["intents"]["assignment"]["basis"], "explicit")
        self.assertEqual(parsed["intents"]["assignment"]["confidence"], 0.9)
        self.assertEqual(parsed["intents"]["assignment"]["evidence"], "change the patient to Soroush")
        # Absent intents are dropped, not carried as present=false.
        self.assertNotIn("append", parsed["intents"])
        self.assertNotIn("out_of_context", parsed["intents"])

    def test_parse_extracts_implicit_assignment_intent(self):
        # A fronted name with no instruction ("Ms. Ghasemi, forehead botox") is implicit.
        parsed = parse_structured_transcription_output(
            '{"transcript": "خانم قاسمی بوتاکس پیشانی.", "language": "fa", '
            '"patient_information": {"raw_mentioned_name": "خانم قاسمی"}, '
            '"intents": {"assignment": {"present": true, "basis": "implicit", "confidence": 0.6}}}'
        )

        self.assertEqual(parsed["intents"]["assignment"]["present"], True)
        self.assertEqual(parsed["intents"]["assignment"]["basis"], "implicit")

    def test_parse_tolerates_missing_or_malformed_intents(self):
        parsed = parse_structured_transcription_output(
            '{"transcript": "ok", "language": "en", "patient_information": {}, "clinical_summary": null, "uncertainties": []}'
        )
        self.assertEqual(parsed["transcript"], "ok")
        self.assertIsNone(parsed["intents"])

        # A malformed intents payload must not invalidate an otherwise usable transcript.
        parsed2 = parse_structured_transcription_output(
            '{"transcript": "ok2", "language": "en", "patient_information": {}, "intents": "nonsense"}'
        )
        self.assertEqual(parsed2["transcript"], "ok2")
        self.assertIsNone(parsed2["intents"])

    def test_parse_normalizes_unknown_assignment_basis_and_out_of_range_confidence(self):
        parsed = parse_structured_transcription_output(
            '{"transcript": "ok", "language": "en", "patient_information": {}, '
            '"intents": {"assignment": {"present": true, "basis": "weird", "confidence": 5}}}'
        )

        self.assertEqual(parsed["intents"]["assignment"]["basis"], "implicit")
        self.assertEqual(parsed["intents"]["assignment"]["confidence"], 1.0)

    def test_prompt_includes_intent_classification_guidance(self):
        prompt = transcription_prompt(None)

        self.assertIn("intents", prompt)
        self.assertIn("basis='explicit'", prompt)

    def test_fixture_audio_output_includes_null_intents(self):
        output = completed_audio_metadata(
            {"id": "job-1", "jobType": "audio_capture_process", "inputArtifactIds": ["artifact-1"]},
            {"type": "audio", "metadata": {"original_filename": "audio_01_initial_consultation.wav"}},
            content=None,
        )

        self.assertIn("intents", output)
        self.assertIsNone(output["intents"])


if __name__ == "__main__":
    unittest.main()
