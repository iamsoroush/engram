import unittest
import uuid
from types import SimpleNamespace

from app.services.patient_assignment_timeline import (
    active_patient_assignment_event,
    append_patient_assignment_event,
    assignment_source_for_event,
    patient_assignment_event,
)


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
        db = _FakeDb([previous_capture_id, None])

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
        db = _FakeDb([newer_capture_id, older_capture_id])

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


if __name__ == "__main__":
    unittest.main()
