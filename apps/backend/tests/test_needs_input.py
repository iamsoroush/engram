import unittest
import uuid
from datetime import datetime, timezone
from typing import Any

from app.models import Session, SessionStatus
from app.services.patient_memory import (
    ACTIVE_SESSION_STATUSES,
    _needs_input_items,
    _session_needs_input_item,
)


def _session(
    *,
    status: SessionStatus,
    patient_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> Session:
    session = Session()
    session.id = uuid.uuid4()
    session.status = status
    session.patient_id = patient_id
    session.updated_at = datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)
    session.extracted_metadata = metadata or {}
    return session


class ActiveSessionStatusesTests(unittest.TestCase):
    def test_resting_states_are_not_active(self) -> None:
        # The whole point of the fix: a processed visit settles into needs_review, which must NOT
        # count as "active" — otherwise every patient looks active.
        self.assertNotIn(SessionStatus.needs_review, ACTIVE_SESSION_STATUSES)
        self.assertNotIn(SessionStatus.reviewing, ACTIVE_SESSION_STATUSES)

    def test_in_progress_states_are_active(self) -> None:
        self.assertEqual(
            ACTIVE_SESSION_STATUSES,
            {SessionStatus.draft, SessionStatus.processing, SessionStatus.reopened},
        )


class SessionNeedsInputItemTests(unittest.TestCase):
    def test_unassigned_without_candidate_needs_assignment(self) -> None:
        item = _session_needs_input_item(_session(status=SessionStatus.unassigned))
        assert item is not None
        self.assertEqual(item["kind"], "assign-patient")

    def test_unassigned_possible_match_needs_choice(self) -> None:
        item = _session_needs_input_item(
            _session(
                status=SessionStatus.unassigned,
                metadata={"patient_match": {"status": "possible_match", "risks": []}},
            )
        )
        assert item is not None
        self.assertEqual(item["kind"], "choose-patient")

    def test_national_id_conflict_is_a_conflict(self) -> None:
        item = _session_needs_input_item(
            _session(
                status=SessionStatus.unassigned,
                metadata={
                    "patient_match": {
                        "status": "possible_match",
                        "risks": ["A provided national ID conflicts with the matched patient."],
                    }
                },
            )
        )
        assert item is not None
        self.assertEqual(item["kind"], "resolve-conflict")

    def test_ai_created_patient_needs_verification(self) -> None:
        # An AI-created patient is assigned (so the visit may even be "complete"), but its identity
        # is unconfirmed — that is the verify category, independent of completeness.
        item = _session_needs_input_item(
            _session(
                status=SessionStatus.needs_review,
                patient_id=uuid.uuid4(),
                metadata={"ai_patient_action": {"needsVerification": True, "status": "needs_verification"}},
            )
        )
        assert item is not None
        self.assertEqual(item["kind"], "verify")

    def test_verified_ai_patient_needs_nothing(self) -> None:
        item = _session_needs_input_item(
            _session(
                status=SessionStatus.needs_review,
                patient_id=uuid.uuid4(),
                metadata={"ai_patient_action": {"needsVerification": False, "status": "verified"}},
            )
        )
        self.assertIsNone(item)

    def test_assigned_resting_visit_needs_nothing(self) -> None:
        # A processed + assigned visit settling in needs_review is no longer a routine
        # "review summary" needs-input item.
        item = _session_needs_input_item(
            _session(status=SessionStatus.needs_review, patient_id=uuid.uuid4())
        )
        self.assertIsNone(item)

    def test_active_assigned_visit_needs_nothing(self) -> None:
        item = _session_needs_input_item(
            _session(status=SessionStatus.draft, patient_id=uuid.uuid4())
        )
        self.assertIsNone(item)


class NeedsInputItemsTests(unittest.TestCase):
    def test_collects_only_qualifying_sessions_with_stable_ids(self) -> None:
        patient_id = str(uuid.uuid4())
        sessions = [
            _session(status=SessionStatus.needs_review, patient_id=uuid.uuid4()),  # resting → none
            _session(status=SessionStatus.unassigned),  # assign-patient
            _session(
                status=SessionStatus.needs_review,
                patient_id=uuid.uuid4(),
                metadata={"ai_patient_action": {"needsVerification": True}},
            ),  # verify
        ]
        items = _needs_input_items(patient_id, sessions)
        self.assertEqual([item["kind"] for item in items], ["assign-patient", "verify"])
        for item in items:
            self.assertTrue(item["id"].startswith(f"{patient_id}:"))
            self.assertIn(item["kind"], item["id"])


if __name__ == "__main__":
    unittest.main()
