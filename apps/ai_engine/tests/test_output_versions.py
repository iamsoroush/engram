"""Every job output envelope stamps its contract ``OUTPUT_VERSION`` (``schemaVersion``, §2.2) and its
prompt's ``PROMPT_VERSION`` (``promptVersion``, §3.3).

Provenance the backend/eval can key regressions on. Additive: both fields are new, never removed a key.
"""
import unittest
from unittest.mock import patch

from ai_engine.contracts.capture import CAPTURE_INTELLIGENCE_OUTPUT_VERSION
from ai_engine.contracts.caption import CAPTION_OUTPUT_VERSION
from ai_engine.contracts.memory import PATIENT_MEMORY_OUTPUT_VERSION
from ai_engine.contracts.qa import QA_DRAFT_OUTPUT_VERSION, QA_REVISE_OUTPUT_VERSION
from ai_engine.contracts.synthesis import SESSION_SYNTHESIS_OUTPUT_VERSION
from ai_engine.jobs.capture_audio import completed_audio_metadata
from ai_engine.jobs.capture_photo import caption_output_metadata
from ai_engine.jobs.patient_memory import completed_patient_memory_output
from ai_engine.jobs.qa_draft import completed_qa_draft_output
from ai_engine.jobs.qa_revise import completed_qa_revise_output
from ai_engine.prompts.caption import PROMPT_VERSION as CAPTION_PROMPT_VERSION
from ai_engine.prompts.patient_memory import PROMPT_VERSION as PATIENT_MEMORY_PROMPT_VERSION
from ai_engine.prompts.qa_draft import PROMPT_VERSION as QA_DRAFT_PROMPT_VERSION
from ai_engine.prompts.qa_revise import PROMPT_VERSION as QA_REVISE_PROMPT_VERSION
from ai_engine.prompts.transcription import PROMPT_VERSION as TRANSCRIPTION_PROMPT_VERSION


class OutputVersionStampTests(unittest.TestCase):
    def test_audio_envelope_stamps_capture_intelligence_version(self):
        out = completed_audio_metadata(
            {"id": "job-1", "jobType": "audio_capture_process", "inputArtifactIds": []},
            {"type": "audio", "metadata": {"original_filename": "audio_01_initial_consultation.wav"}},
            content=None,
        )
        self.assertEqual(out["schemaVersion"], CAPTURE_INTELLIGENCE_OUTPUT_VERSION)
        self.assertEqual(out["promptVersion"], TRANSCRIPTION_PROMPT_VERSION)

    def test_caption_envelope_stamps_caption_version(self):
        out = caption_output_metadata(
            {"id": "job-1", "jobType": "image_capture_process", "inputArtifactIds": []},
            {"caption": "A caption.", "confidence": 0.9, "outOfContext": None, "pairing": {}, "uncertainties": []},
        )
        self.assertEqual(out["schemaVersion"], CAPTION_OUTPUT_VERSION)
        self.assertEqual(out["promptVersion"], CAPTION_PROMPT_VERSION)

    def test_patient_memory_fallback_stamps_version(self):
        with patch("ai_engine.jobs.patient_memory.transcription_is_configured", return_value=False):
            out = completed_patient_memory_output({"deterministicFallback": {"summary": "s"}})
        self.assertEqual(out["schemaVersion"], PATIENT_MEMORY_OUTPUT_VERSION)
        self.assertEqual(out["promptVersion"], PATIENT_MEMORY_PROMPT_VERSION)

    def test_qa_draft_fallback_stamps_version(self):
        with patch("ai_engine.jobs.qa_draft.transcription_is_configured", return_value=False):
            out = completed_qa_draft_output({"deterministicFallback": {"draft": "d"}})
        self.assertEqual(out["schemaVersion"], QA_DRAFT_OUTPUT_VERSION)
        self.assertEqual(out["promptVersion"], QA_DRAFT_PROMPT_VERSION)

    def test_qa_revise_fallback_stamps_version(self):
        with patch("ai_engine.jobs.qa_revise.transcription_is_configured", return_value=False):
            out = completed_qa_revise_output({"deterministicFallback": {"reply": "r"}}, b"")
        self.assertEqual(out["schemaVersion"], QA_REVISE_OUTPUT_VERSION)
        self.assertEqual(out["promptVersion"], QA_REVISE_PROMPT_VERSION)

    def test_synthesis_structured_report_carries_version(self):
        # Synthesis embeds its OUTPUT_VERSION inside structured_report (already first-class backend-side).
        from ai_engine.contracts.synthesis import parse_session_synthesis_output

        out = parse_session_synthesis_output('{"summary":"S"}', source_capture_ids=[])
        self.assertEqual(out["schemaVersion"], SESSION_SYNTHESIS_OUTPUT_VERSION)


if __name__ == "__main__":
    unittest.main()
