import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from app.models import PatientStatus
from app.services.patient_assignment_timeline import (
    active_patient_assignment_event,
    append_patient_assignment_event,
    archive_orphaned_ai_patient,
    assignment_source_for_event,
    patient_assignment_event,
)
from app.services.patients import AI_CREATED_PATIENT_NOTE


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDb:
    def __init__(self, values):
        self.values = list(values)

    def execute(self, _statement):
        return _ScalarResult(self.values.pop(0))


class PatientAssignmentTimelineTests(unittest.TestCase):
    def test_latest_deleted_capture_falls_back_to_previous_assignment_source(self):
        tenant_id = uuid.uuid4()
        session_id = uuid.uuid4()
        previous_capture_id = uuid.uuid4()
        deleted_capture_id = uuid.uuid4()
        previous_event = patient_assignment_event(
            source="ai-engine",
            action="matched_and_assigned",
            patient_id=uuid.uuid4(),
            display_name="Previous patient",
            reason="Previous audio identity matched.",
            capture_id=previous_capture_id,
            assigned_at="2026-06-03T10:00:00+00:00",
        )
        deleted_event = patient_assignment_event(
            source="ai-engine",
            action="created_and_assigned",
            patient_id=uuid.uuid4(),
            display_name="Deleted patient",
            reason="Deleted audio identity created a patient.",
            capture_id=deleted_capture_id,
            created=True,
            assigned_at="2026-06-03T11:00:00+00:00",
        )
        session = SimpleNamespace(
            tenant_id=tenant_id,
            id=session_id,
            extracted_metadata={"patient_assignment_timeline": [previous_event, deleted_event]},
        )
        # active_patient_assignment_event now loads the Capture row to skip out-of-context captures,
        # so the existence probe returns a capture-like object (in-context) or None (deleted/gone).
        db = _FakeDb([SimpleNamespace(capture_metadata=None), None])

        self.assertEqual(active_patient_assignment_event(db, session), previous_event)

    def test_active_assignment_uses_effective_time_not_append_order(self):
        tenant_id = uuid.uuid4()
        session_id = uuid.uuid4()
        older_capture_id = uuid.uuid4()
        newer_capture_id = uuid.uuid4()
        newer_event = patient_assignment_event(
            source="ai-engine",
            action="matched_and_assigned",
            patient_id=uuid.uuid4(),
            display_name="Newer patient",
            reason="Newer audio identity matched.",
            capture_id=newer_capture_id,
            effective_at="2026-06-03T12:00:00+00:00",
        )
        older_reprocessed_event = patient_assignment_event(
            source="ai-engine",
            action="matched_and_assigned",
            patient_id=uuid.uuid4(),
            display_name="Older patient",
            reason="Older audio identity was retried later.",
            capture_id=older_capture_id,
            effective_at="2026-06-03T10:00:00+00:00",
        )
        session = SimpleNamespace(
            tenant_id=tenant_id,
            id=session_id,
            extracted_metadata={"patient_assignment_timeline": [newer_event, older_reprocessed_event]},
        )
        db = _FakeDb([SimpleNamespace(capture_metadata=None), SimpleNamespace(capture_metadata=None)])

        self.assertEqual(active_patient_assignment_event(db, session), newer_event)

    def test_assignment_source_distinguishes_ai_creation_and_match(self):
        self.assertEqual(assignment_source_for_event({"source": "staff"}), "staff")
        self.assertEqual(assignment_source_for_event({"source": "ai-engine", "created": True}), "ai_created")
        self.assertEqual(assignment_source_for_event({"source": "ai-engine", "created": False}), "ai_matched")

    def test_append_bootstraps_legacy_ai_action_as_previous_timeline_event(self):
        legacy_patient_id = uuid.uuid4()
        legacy_capture_id = uuid.uuid4()
        next_event = patient_assignment_event(
            source="ai-engine",
            action="matched_and_assigned",
            patient_id=uuid.uuid4(),
            display_name="Next patient",
            reason="Next audio identity matched.",
            capture_id=uuid.uuid4(),
        )

        metadata = append_patient_assignment_event(
            {
                "ai_patient_action": {
                    "source": "ai-engine",
                    "action": "created_and_assigned",
                    "basisCaptureId": str(legacy_capture_id),
                    "patientId": str(legacy_patient_id),
                    "displayName": "Legacy patient",
                    "created": True,
                    "assigned": True,
                }
            },
            next_event,
        )

        self.assertEqual(len(metadata["patient_assignment_timeline"]), 2)
        self.assertEqual(metadata["patient_assignment_timeline"][0]["captureId"], str(legacy_capture_id))
        self.assertTrue(metadata["patient_assignment_timeline"][0]["created"])
        self.assertEqual(metadata["patient_assignment_timeline"][1], next_event)


class OutOfContextAssignmentBasisTests(unittest.TestCase):
    """A-F4: an out-of-context capture is not a valid assignment basis."""

    def test_out_of_context_capture_is_excluded(self):
        capture_id = uuid.uuid4()
        event = patient_assignment_event(
            source="ai-engine", action="matched_and_assigned", patient_id=uuid.uuid4(),
            display_name="P", reason="r", capture_id=capture_id,
        )
        session = SimpleNamespace(
            tenant_id=uuid.uuid4(), id=uuid.uuid4(),
            extracted_metadata={"patient_assignment_timeline": [event]},
        )
        ooc_capture = SimpleNamespace(capture_metadata={"out_of_context": {"present": True}})
        db = _FakeDb([ooc_capture])
        self.assertIsNone(active_patient_assignment_event(db, session))

    def test_staff_overridden_ooc_capture_is_still_a_valid_basis(self):
        capture_id = uuid.uuid4()
        event = patient_assignment_event(
            source="ai-engine", action="matched_and_assigned", patient_id=uuid.uuid4(),
            display_name="P", reason="r", capture_id=capture_id,
        )
        session = SimpleNamespace(
            tenant_id=uuid.uuid4(), id=uuid.uuid4(),
            extracted_metadata={"patient_assignment_timeline": [event]},
        )
        relevant_capture = SimpleNamespace(
            capture_metadata={"out_of_context": {"present": True, "overridden_by_staff": True}}
        )
        db = _FakeDb([relevant_capture])
        self.assertEqual(active_patient_assignment_event(db, session), event)


class _ArchiveDb:
    """Minimal DB stub for archive_orphaned_ai_patient: one patient, then scripted dependency probes."""

    def __init__(self, patient, probes):
        self.patient = patient
        self.probes = list(probes)

    def get(self, _model, _ident):
        return self.patient

    def execute(self, _statement):
        return SimpleNamespace(scalar_one_or_none=lambda: self.probes.pop(0))


class OrphanArchiveTests(unittest.TestCase):
    """Incident Fix 6: reassigning away from an unreferenced AI-created patient archives it."""

    def _patient(self):
        return SimpleNamespace(
            id=uuid.uuid4(), tenant_id=uuid.uuid4(), status=PatientStatus.active, notes=AI_CREATED_PATIENT_NOTE
        )

    def test_unreferenced_ai_patient_is_archived(self):
        patient = self._patient()
        db = _ArchiveDb(patient, probes=[None, None])  # no session, no capture
        with (
            patch("app.auth.service.audit"),
            patch("app.services.feedback.record_feedback_event"),
        ):
            archived = archive_orphaned_ai_patient(db, patient_id=patient.id, actor_user_id=None)
        self.assertTrue(archived)
        self.assertEqual(patient.status, PatientStatus.archived)

    def test_ai_patient_with_remaining_session_is_not_archived(self):
        patient = self._patient()
        db = _ArchiveDb(patient, probes=[uuid.uuid4(), None])  # still has a session
        archived = archive_orphaned_ai_patient(db, patient_id=patient.id, actor_user_id=None)
        self.assertFalse(archived)
        self.assertEqual(patient.status, PatientStatus.active)

    def test_verified_patient_is_never_archived(self):
        patient = self._patient()
        patient.notes = "A real clinical note"  # no longer the AI-creation breadcrumb
        db = _ArchiveDb(patient, probes=[None, None])
        self.assertFalse(archive_orphaned_ai_patient(db, patient_id=patient.id, actor_user_id=None))
        self.assertEqual(patient.status, PatientStatus.active)


if __name__ == "__main__":
    unittest.main()
