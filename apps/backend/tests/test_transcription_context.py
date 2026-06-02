import unittest
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.models import CaptureStatus, CaptureType, SessionStatus
from app.services.ai_jobs import transcription_context_from_inputs


def capture(**overrides):
    values = {
        "id": uuid.uuid4(),
        "status": CaptureStatus.processed,
        "capture_type": CaptureType.audio,
        "capture_metadata": {},
        "captured_at": datetime(2026, 6, 2, 8, 0, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class TranscriptionContextTests(unittest.TestCase):
    def test_context_includes_assigned_patient_previous_transcripts_and_notes(self):
        tenant_id = uuid.uuid4()
        session_id = uuid.uuid4()
        current_capture_id = uuid.uuid4()
        session = SimpleNamespace(
            id=session_id,
            tenant_id=tenant_id,
            status=SessionStatus.needs_review,
            title="Cheek filler follow-up",
            summary="Follow-up visit",
            created_at=datetime(2026, 6, 2, 7, 45, tzinfo=timezone.utc),
            updated_at=datetime(2026, 6, 2, 8, 10, tzinfo=timezone.utc),
            captured_at=datetime(2026, 6, 2, 8, 0, tzinfo=timezone.utc),
        )
        previous_audio = capture(
            capture_metadata={"transcript": {"text": "Patient mentioned mild left cheek asymmetry."}},
        )
        previous_note = capture(
            capture_type=CaptureType.note,
            capture_metadata={"detail": "Prefers conservative correction."},
        )
        current_audio = capture(id=current_capture_id, capture_metadata={"transcript": {"text": "Do not include me."}})

        context = transcription_context_from_inputs(
            session=session,
            clinic={"name": "AesMem Clinic", "assumptions": ["Persian/Iranian aesthetics clinic."]},
            assigned_patient={"status": "assigned", "displayName": "Sara N.", "nationalId": "0012345678"},
            patient_history_summary="Prior cheek filler, no allergy noted.",
            captures=[previous_audio, previous_note, current_audio],
            current_capture_id=current_capture_id,
        )

        self.assertEqual(context["schemaVersion"], "2026-06-02.audio-transcription-context.v1")
        self.assertEqual(context["assignedPatient"]["displayName"], "Sara N.")
        self.assertEqual(context["patientSummarizedHistory"], "Prior cheek filler, no allergy noted.")
        self.assertEqual(context["session"]["title"], "Cheek filler follow-up")
        self.assertEqual(context["previousTranscripts"][0]["text"], "Patient mentioned mild left cheek asymmetry.")
        self.assertEqual(context["textNotes"][0]["text"], "Prefers conservative correction.")
        self.assertNotIn("Do not include me.", str(context))


if __name__ == "__main__":
    unittest.main()
