import unittest
from unittest.mock import patch

from ai_engine.processing import (
    audio_to_flac_mono_16khz_base64,
    completed_audio_metadata,
    parse_structured_transcription_output,
    transcription_prompt,
)


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
                "clinic": {"name": "AesMem Clinic"},
                "assignedPatient": {"displayName": "Sara N."},
                "previousTranscripts": [{"text": "Previous cheek filler note."}],
                "textNotes": [{"text": "Prefers subtle correction."}],
            }
        )

        self.assertIn("Persian/Farsi", prompt)
        self.assertIn("Iranian national IDs", prompt)
        self.assertIn("AesMem Clinic", prompt)
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


if __name__ == "__main__":
    unittest.main()
