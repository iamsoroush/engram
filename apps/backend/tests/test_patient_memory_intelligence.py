import unittest
import uuid
from datetime import datetime, timedelta, timezone

from app.models import Patient, Session
from app.services.patient_memory_intelligence import (
    MOCK_AI_SOURCE,
    MOCK_DETERMINISTIC_SOURCE,
    MOCK_MEMORY_DELAY_SECONDS,
    apply_patient_memory_output,
    build_patient_memory_job_input,
    finalize_patient_memory_if_due,
    generate_patient_memory,
    mark_patient_memory_updating,
    memory_status,
    persisted_summary,
    stored_history,
)


def _session(captured_at: datetime, *, capture_count: int, latest_type: str) -> Session:
    session = Session()
    session.id = uuid.uuid4()
    session.captured_at = captured_at
    session.updated_at = captured_at
    session.created_at = captured_at
    session.extracted_metadata = {"capture_count": capture_count, "latest_capture_type": latest_type}
    return session


def _patient(name: str = "Sara Nazari") -> Patient:
    patient = Patient()
    patient.id = uuid.uuid4()
    patient.display_name = name
    patient.memory = None
    return patient


class GeneratePatientMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        base = datetime(2026, 6, 7, 17, 35, tzinfo=timezone.utc)
        self.patient = _patient()
        self.sessions = [
            _session(base, capture_count=1, latest_type="audio"),
            _session(base - timedelta(days=3), capture_count=2, latest_type="photo"),
        ]

    def test_pro_is_synthesized_brief(self) -> None:
        content = generate_patient_memory(self.patient, self.sessions, "pro")
        self.assertEqual(content["mode"], "pro")
        self.assertEqual(content["source"], MOCK_AI_SOURCE)
        history = content["history"]
        self.assertEqual(history["mode"], "pro")
        labels = [section["label"] for section in history["sections"]]
        self.assertEqual(labels, ["Story so far", "Worth remembering", "Right now"])
        self.assertEqual(history["visits"], [])
        self.assertIn("Sara Nazari", content["summary"])

    def test_basic_is_structural_recap_without_audio_topic(self) -> None:
        content = generate_patient_memory(self.patient, self.sessions, "basic")
        self.assertEqual(content["mode"], "basic")
        self.assertEqual(content["source"], MOCK_DETERMINISTIC_SOURCE)
        history = content["history"]
        self.assertEqual(history["sections"], [])
        self.assertEqual(len(history["visits"]), 2)
        # The audio visit notes a saved transcript but never paraphrases its content.
        self.assertIn("Transcript saved", history["visits"][0])
        self.assertIn("an audio note", history["visits"][0])

    def test_no_sessions_is_safe(self) -> None:
        for tier in ("pro", "basic"):
            content = generate_patient_memory(self.patient, [], tier)
            self.assertTrue(content["summary"])
            self.assertTrue(content["history"]["snapshot"])


class MemoryLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.patient = _patient()
        self.sessions = [_session(datetime(2026, 6, 7, tzinfo=timezone.utc), capture_count=1, latest_type="audio")]

    def test_finalize_skips_when_not_updating(self) -> None:
        self.assertEqual(memory_status(self.patient), "ready")
        self.assertFalse(finalize_patient_memory_if_due(None, self.patient, self.sessions, "pro"))

    def test_updating_then_due_finalizes(self) -> None:
        now = datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)
        mark_patient_memory_updating(_FakeDb(self.patient), self.patient.id, now=now)
        self.assertEqual(memory_status(self.patient), "updating")

        # Before the imitated latency elapses, the read does not finalize.
        too_soon = now + timedelta(seconds=MOCK_MEMORY_DELAY_SECONDS - 1)
        self.assertFalse(finalize_patient_memory_if_due(None, self.patient, self.sessions, "pro", now=too_soon))
        self.assertEqual(memory_status(self.patient), "updating")
        self.assertIsNone(persisted_summary(self.patient))

        # After it elapses, the next read finalizes to ready with tier-aware content.
        due = now + timedelta(seconds=MOCK_MEMORY_DELAY_SECONDS + 1)
        self.assertTrue(finalize_patient_memory_if_due(None, self.patient, self.sessions, "pro", now=due))
        self.assertEqual(memory_status(self.patient), "ready")
        self.assertTrue(persisted_summary(self.patient))
        self.assertEqual(self.patient.memory["source"], MOCK_AI_SOURCE)
        self.assertEqual(self.patient.memory["mode"], "pro")

    def test_basic_finalizes_deterministic_source(self) -> None:
        now = datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)
        mark_patient_memory_updating(_FakeDb(self.patient), self.patient.id, now=now)
        due = now + timedelta(seconds=MOCK_MEMORY_DELAY_SECONDS + 1)
        self.assertTrue(finalize_patient_memory_if_due(None, self.patient, self.sessions, "basic", now=due))
        self.assertEqual(self.patient.memory["source"], MOCK_DETERMINISTIC_SOURCE)


class _FakeDb:
    """Minimal stand-in for a DB session so mark_patient_memory_updating can resolve a patient."""

    def __init__(self, patient: Patient) -> None:
        self._patient = patient

    def get(self, _model, patient_id):  # noqa: ANN001 - test stub
        return self._patient if patient_id == self._patient.id else None


class PatientMemoryJobTests(unittest.TestCase):
    def setUp(self) -> None:
        base = datetime(2026, 6, 7, 17, 35, tzinfo=timezone.utc)
        self.patient = _patient()
        self.sessions = [
            _session(base, capture_count=1, latest_type="audio"),
            _session(base - timedelta(days=3), capture_count=2, latest_type="photo"),
        ]

    def test_build_job_input_is_incremental(self) -> None:
        self.patient.memory = {"status": "ready", "summary": "Prior summary.", "history": {"snapshot": "Prior."}}
        job_input = build_patient_memory_job_input(self.patient, self.sessions, "pro", language="en")
        self.assertEqual(job_input["tier"], "pro")
        self.assertEqual(job_input["language"], "en")
        # The model gets prior memory + compact per-visit briefs (not raw transcripts) + a fallback.
        self.assertEqual(job_input["patient"]["priorMemory"]["summary"], "Prior summary.")
        self.assertEqual(len(job_input["patient"]["sessions"]), 2)
        self.assertIn("date", job_input["patient"]["sessions"][0])
        self.assertTrue(job_input["deterministicFallback"]["summary"])
        self.assertIn("history", job_input["deterministicFallback"])

    def test_apply_valid_ai_output(self) -> None:
        output = {
            "summary": "Synthesized one-liner.",
            "history": {
                "snapshot": "Sara · maintenance.",
                "sections": [{"label": "Story so far", "body": "She came back."}],
                "visits": [],
            },
            "source": "ai:some-model",
        }
        apply_patient_memory_output(self.patient, output, "pro")
        self.assertEqual(memory_status(self.patient), "ready")
        self.assertEqual(persisted_summary(self.patient), "Synthesized one-liner.")
        self.assertEqual(self.patient.memory["source"], "ai:some-model")
        history = stored_history(self.patient)
        self.assertEqual(history["mode"], "pro")
        self.assertEqual(history["sections"][0]["label"], "Story so far")

    def test_apply_bad_output_falls_back(self) -> None:
        # Missing summary → defensive deterministic fallback rather than writing junk.
        apply_patient_memory_output(self.patient, {"history": {}}, "pro")
        self.assertEqual(memory_status(self.patient), "ready")
        self.assertTrue(persisted_summary(self.patient))
        self.assertTrue(stored_history(self.patient)["snapshot"])


if __name__ == "__main__":
    unittest.main()
