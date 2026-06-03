import unittest
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.services.ai_jobs import (
    assignment_intent_basis,
    earliest_pending_capture_job,
    near_match_suggestion,
    out_of_context_marker,
    should_apply_identity_assignment,
    suggested_reassignment_candidate,
    tenant_tier,
)


class _TierDb:
    def __init__(self, value):
        self.value = value

    def execute(self, _statement):
        return SimpleNamespace(scalar_one_or_none=lambda: self.value)


class TenantTierTests(unittest.TestCase):
    def test_known_tiers_pass_through(self):
        self.assertEqual(tenant_tier(_TierDb("basic"), uuid.uuid4()), "basic")
        self.assertEqual(tenant_tier(_TierDb("pro"), uuid.uuid4()), "pro")

    def test_missing_or_unknown_defaults_to_pro(self):
        self.assertEqual(tenant_tier(_TierDb(None), uuid.uuid4()), "pro")
        self.assertEqual(tenant_tier(_TierDb("enterprise"), uuid.uuid4()), "pro")


class AssignmentIntentBasisTests(unittest.TestCase):
    def test_returns_basis_when_assignment_present(self):
        self.assertEqual(
            assignment_intent_basis({"intents": {"assignment": {"present": True, "basis": "explicit"}}}),
            "explicit",
        )
        self.assertEqual(
            assignment_intent_basis({"intents": {"assignment": {"present": True, "basis": "implicit"}}}),
            "implicit",
        )

    def test_unknown_basis_defaults_to_implicit(self):
        self.assertEqual(
            assignment_intent_basis({"intents": {"assignment": {"present": True, "basis": "weird"}}}),
            "implicit",
        )

    def test_absent_or_not_present_returns_none(self):
        self.assertIsNone(assignment_intent_basis({}))
        self.assertIsNone(assignment_intent_basis({"intents": None}))
        self.assertIsNone(assignment_intent_basis({"intents": {"assignment": {"present": False}}}))


class IdentityAssignmentGateTests(unittest.TestCase):
    def test_first_identity_on_unassigned_visit_applies_regardless_of_basis(self):
        for basis in (None, "implicit", "explicit"):
            self.assertTrue(
                should_apply_identity_assignment(has_session=True, has_existing_patient=False, assignment_basis=basis)
            )

    def test_assigned_visit_overrides_only_on_explicit(self):
        self.assertTrue(
            should_apply_identity_assignment(has_session=True, has_existing_patient=True, assignment_basis="explicit")
        )
        self.assertFalse(
            should_apply_identity_assignment(has_session=True, has_existing_patient=True, assignment_basis="implicit")
        )
        self.assertFalse(
            should_apply_identity_assignment(has_session=True, has_existing_patient=True, assignment_basis=None)
        )

    def test_no_session_never_applies(self):
        self.assertFalse(
            should_apply_identity_assignment(has_session=False, has_existing_patient=False, assignment_basis="explicit")
        )


class SuggestedReassignmentTests(unittest.TestCase):
    def test_wraps_match_as_unapplied_suggestion(self):
        current_patient_id = uuid.uuid4()
        session = SimpleNamespace(tenant_id=uuid.uuid4(), patient_id=current_patient_id)
        fake_match = {"decision": "matched", "patientId": str(uuid.uuid4()), "displayName": "Ms Ghasemi"}

        with patch("app.services.ai_jobs.match_patient_from_patient_information", return_value=fake_match):
            candidate = suggested_reassignment_candidate(
                object(),
                tenant_id=session.tenant_id,
                session=session,
                patient_information={"raw_mentioned_name": "خانم قاسمی"},
            )

        self.assertEqual(candidate["decision"], "suggested_reassignment")
        self.assertEqual(candidate["status"], "suggested_reassignment")
        self.assertFalse(candidate["appliedAutomatically"])
        self.assertEqual(candidate["currentPatientId"], str(current_patient_id))
        # Carries the underlying match target so the UI can offer "reassign to X".
        self.assertEqual(candidate["displayName"], "Ms Ghasemi")


class NearMatchSuggestionTests(unittest.TestCase):
    def _possible_match(self, candidates):
        return {"decision": "possible_match", "candidateSet": candidates, "patientId": None}

    def test_dominant_high_confidence_becomes_actionable_suggestion(self):
        pid = str(uuid.uuid4())
        candidate = self._possible_match(
            [
                {"patientId": pid, "displayName": "سروش معاصد", "confidence": 0.84},
                {"patientId": str(uuid.uuid4()), "displayName": "Other", "confidence": 0.6},
            ]
        )
        out = near_match_suggestion(candidate, patient_information={"raw_mentioned_name": "سروش معاضد"})

        self.assertIsNotNone(out)
        self.assertEqual(out["decision"], "suggested_reassignment")
        self.assertEqual(out["patientId"], pid)
        self.assertEqual(out["displayName"], "سروش معاصد")
        self.assertFalse(out["appliedAutomatically"])

    def test_tie_at_top_stays_choose_patient(self):
        candidate = self._possible_match(
            [
                {"patientId": str(uuid.uuid4()), "displayName": "نگار احمدی", "confidence": 0.88},
                {"patientId": str(uuid.uuid4()), "displayName": "بابک احمدی", "confidence": 0.88},
            ]
        )
        self.assertIsNone(near_match_suggestion(candidate, patient_information={}))

    def test_below_threshold_returns_none(self):
        candidate = self._possible_match([{"patientId": str(uuid.uuid4()), "displayName": "X", "confidence": 0.6}])
        self.assertIsNone(near_match_suggestion(candidate, patient_information={}))

    def test_non_possible_match_or_empty_returns_none(self):
        self.assertIsNone(near_match_suggestion({"decision": "matched", "candidateSet": []}, patient_information={}))
        self.assertIsNone(near_match_suggestion({"decision": "possible_match", "candidateSet": []}, patient_information={}))
        self.assertIsNone(near_match_suggestion(None, patient_information={}))


class OutOfContextMarkerTests(unittest.TestCase):
    def test_present_intent_becomes_marker(self):
        out = out_of_context_marker(
            {"intents": {"out_of_context": {"present": True, "confidence": 0.9, "reason": "no clinical content"}}}
        )
        self.assertEqual(out, {"present": True, "confidence": 0.9, "reason": "no clinical content", "source": "ai"})

    def test_absent_or_missing_returns_none(self):
        self.assertIsNone(out_of_context_marker({}))
        self.assertIsNone(out_of_context_marker({"intents": {"out_of_context": {"present": False}}}))
        self.assertIsNone(out_of_context_marker({"intents": {}}))
        self.assertIsNone(out_of_context_marker({"intents": None}))


class CaptureChainOrderingTests(unittest.TestCase):
    def _key(self, minute):
        stamp = datetime(2026, 6, 3, 16, minute, tzinfo=timezone.utc)
        return (stamp, stamp)

    def test_earliest_pending_capture_job_picks_smallest_order(self):
        first, second, third = SimpleNamespace(id="j1"), SimpleNamespace(id="j2"), SimpleNamespace(id="j3")
        ordered = [(self._key(41), second), (self._key(37), first), (self._key(45), third)]
        self.assertIs(earliest_pending_capture_job(ordered), first)

    def test_earliest_pending_capture_job_empty_is_none(self):
        self.assertIsNone(earliest_pending_capture_job([]))


if __name__ == "__main__":
    unittest.main()
