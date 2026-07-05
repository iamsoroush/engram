"""Unit tests for the pure identity/assignment intent helpers (Track E1)."""
import unittest
import uuid
from types import SimpleNamespace

from app.services.ai_jobs.intents import (
    detach_intent_basis,
    explicit_no_effect_notice,
    fuzzy_auto_apply_candidate,
    inert_assignment_conflict,
    name_correction_suggestion,
    resolved_match_patient_id,
    similar_existing_note,
    suggested_unassign_candidate,
)
from app.services.captures import _capture_drove_assignment
from app.services.patient_matching import NATIONAL_ID_NAME_MISMATCH_RISK


def _session(patient_id=None):
    return SimpleNamespace(patient_id=patient_id)


class DetachIntentTests(unittest.TestCase):
    def test_present_with_basis(self):
        self.assertEqual(detach_intent_basis({"intents": {"detach": {"present": True, "basis": "implicit"}}}), "implicit")

    def test_present_defaults_to_explicit(self):
        self.assertEqual(detach_intent_basis({"intents": {"detach": {"present": True}}}), "explicit")

    def test_absent(self):
        self.assertIsNone(detach_intent_basis({"intents": {"detach": {"present": False}}}))
        self.assertIsNone(detach_intent_basis({"intents": {}}))
        self.assertIsNone(detach_intent_basis({}))


class ResolvedMatchPatientIdTests(unittest.TestCase):
    def test_exact_matched(self):
        pid = str(uuid.uuid4())
        self.assertEqual(resolved_match_patient_id({"decision": "matched", "patientId": pid}), pid)

    def test_dominant_fuzzy(self):
        pid = str(uuid.uuid4())
        candidate = {"decision": "possible_match", "candidateSet": [{"patientId": pid, "confidence": 0.85}]}
        self.assertEqual(resolved_match_patient_id(candidate), pid)

    def test_below_threshold_is_none(self):
        candidate = {"decision": "possible_match", "candidateSet": [{"patientId": str(uuid.uuid4()), "confidence": 0.6}]}
        self.assertIsNone(resolved_match_patient_id(candidate))

    def test_no_match_is_none(self):
        self.assertIsNone(resolved_match_patient_id({"decision": "no_match", "candidateSet": []}))


class FuzzyAutoApplyGuardTests(unittest.TestCase):
    def test_name_mismatch_risk_blocks_auto_apply(self):
        candidate = {
            "decision": "possible_match",
            "risks": [NATIONAL_ID_NAME_MISMATCH_RISK],
            "candidateSet": [{"patientId": str(uuid.uuid4()), "confidence": 1.0, "risks": [NATIONAL_ID_NAME_MISMATCH_RISK]}],
        }
        self.assertIsNone(fuzzy_auto_apply_candidate(candidate, strictness="lenient", assignment_basis="explicit"))


class SuggestionShapeTests(unittest.TestCase):
    def test_name_correction_suggestion(self):
        session = _session(patient_id=uuid.uuid4())
        result = name_correction_suggestion(
            session=session, current_display_name="سورنا معاضد",
            patient_information={"raw_mentioned_name": "سروش معاضد"},
        )
        self.assertEqual(result["status"], "suggested_name_correction")
        self.assertEqual(result["proposedName"], "سروش معاضد")
        self.assertEqual(result["patientId"], str(session.patient_id))

    def test_suggested_unassign(self):
        session = _session(patient_id=uuid.uuid4())
        result = suggested_unassign_candidate(
            session=session, patient_information=None, current_display_name="Maryam", basis="explicit"
        )
        self.assertEqual(result["status"], "suggested_unassign")
        self.assertIsNone(result["patientId"])

    def test_explicit_no_effect_notice(self):
        session = _session(patient_id=uuid.uuid4())
        result = explicit_no_effect_notice(session=session, patient_information={"raw_mentioned_name": "Sara"})
        self.assertEqual(result["status"], "assignment_no_effect")
        self.assertEqual(result["spokenName"], "Sara")

    def test_similar_existing_note(self):
        match = {"candidateSet": [{"patientId": str(uuid.uuid4()), "displayName": "سورنا معاضد", "confidence": 0.7}]}
        note = similar_existing_note(match)
        self.assertEqual(note["displayName"], "سورنا معاضد")
        self.assertIsNone(similar_existing_note({"candidateSet": []}))

    def test_inert_assignment_conflict(self):
        result = inert_assignment_conflict(
            applied_patient_id="a", applied_display_name="Sara", active_patient_id="b", active_display_name="Maryam"
        )
        self.assertTrue(result["inertAssignment"])
        self.assertEqual(result["status"], "suggested_reassignment")


class CaptureDroveAssignmentTests(unittest.TestCase):
    def test_true_for_assignment_basis(self):
        self.assertTrue(_capture_drove_assignment({"ai_patient_assignment_basis": True}))
        self.assertTrue(_capture_drove_assignment({"ai_patient_action": {"action": "matched_and_assigned"}}))
        self.assertTrue(_capture_drove_assignment({"patient_match_candidate": {"decision": "matched"}}))

    def test_false_for_suggestion_only(self):
        self.assertFalse(_capture_drove_assignment({"patient_match_candidate": {"decision": "suggested_reassignment"}}))
        self.assertFalse(_capture_drove_assignment({}))


if __name__ == "__main__":
    unittest.main()
