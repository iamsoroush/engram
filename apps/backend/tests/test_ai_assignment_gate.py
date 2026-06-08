import unittest
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.services.ai_jobs import (
    assignment_intent_basis,
    earliest_pending_capture_job,
    fuzzy_auto_apply_candidate,
    near_match_suggestion,
    out_of_context_marker,
    should_apply_identity_assignment,
    suggested_reassignment_candidate,
    tenant_match_strictness,
    tenant_tier,
)
from app.services.patient_matching import NATIONAL_ID_CONFLICT_RISK


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


class TenantMatchStrictnessTests(unittest.TestCase):
    def test_known_levels_pass_through(self):
        for level in ("strict", "balanced", "lenient"):
            self.assertEqual(tenant_match_strictness(_TierDb(level), uuid.uuid4()), level)

    def test_missing_or_unknown_defaults_to_strict(self):
        self.assertEqual(tenant_match_strictness(_TierDb(None), uuid.uuid4()), "strict")
        self.assertEqual(tenant_match_strictness(_TierDb("aggressive"), uuid.uuid4()), "strict")


class FuzzyAutoApplyCandidateTests(unittest.TestCase):
    def _possible_match(self, candidates, risks=None):
        return {"decision": "possible_match", "candidateSet": candidates, "risks": risks or []}

    def _single(self, confidence=0.84, risks=None):
        return self._possible_match([{"patientId": str(uuid.uuid4()), "displayName": "سروش معاصد", "confidence": confidence, "risks": risks or []}])

    def test_strict_never_auto_applies_a_fuzzy_match(self):
        self.assertIsNone(fuzzy_auto_apply_candidate(self._single(), strictness="strict", assignment_basis="explicit"))

    def test_balanced_auto_applies_single_high_confidence_explicit(self):
        top = fuzzy_auto_apply_candidate(self._single(0.84), strictness="balanced", assignment_basis="explicit")
        self.assertIsNotNone(top)
        self.assertEqual(top["displayName"], "سروش معاصد")

    def test_balanced_below_threshold_is_suggestion(self):
        self.assertIsNone(fuzzy_auto_apply_candidate(self._single(0.80), strictness="balanced", assignment_basis="explicit"))

    def test_lenient_reaches_lower_threshold(self):
        self.assertIsNotNone(fuzzy_auto_apply_candidate(self._single(0.78), strictness="lenient", assignment_basis="explicit"))

    def test_implicit_basis_never_auto_applies(self):
        self.assertIsNone(fuzzy_auto_apply_candidate(self._single(0.84), strictness="lenient", assignment_basis="implicit"))

    def test_national_id_conflict_guard_blocks_auto_apply_at_every_level(self):
        result_conflict = self._single(0.84, risks=[NATIONAL_ID_CONFLICT_RISK])
        result_conflict["risks"] = [NATIONAL_ID_CONFLICT_RISK]
        self.assertIsNone(fuzzy_auto_apply_candidate(result_conflict, strictness="lenient", assignment_basis="explicit"))

    def test_tie_at_top_stays_choose_patient(self):
        tie = self._possible_match(
            [
                {"patientId": str(uuid.uuid4()), "displayName": "نگار احمدی", "confidence": 0.84},
                {"patientId": str(uuid.uuid4()), "displayName": "بابک احمدی", "confidence": 0.84},
            ]
        )
        self.assertIsNone(fuzzy_auto_apply_candidate(tie, strictness="lenient", assignment_basis="explicit"))


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
        # Matched-vs-spoken identity for the H4 partial-match surface.
        self.assertEqual(candidate["matchedName"], "Ms Ghasemi")
        self.assertEqual(candidate["spokenName"], "خانم قاسمی")

    def test_promotes_dominant_fuzzy_candidate_so_apply_reassigns_existing(self):
        session = SimpleNamespace(tenant_id=uuid.uuid4(), patient_id=uuid.uuid4())
        pid = str(uuid.uuid4())
        # A possible_match carries no top-level patientId; the dominant candidate is promoted.
        fuzzy = {
            "decision": "possible_match",
            "patientId": None,
            "displayName": None,
            "candidateSet": [{"patientId": pid, "displayName": "سروش معاصد", "confidence": 0.84}],
        }
        with patch("app.services.ai_jobs.match_patient_from_patient_information", return_value=fuzzy):
            candidate = suggested_reassignment_candidate(
                object(),
                tenant_id=session.tenant_id,
                session=session,
                patient_information={"raw_mentioned_name": "سروش معاضد"},
            )
        self.assertEqual(candidate["patientId"], pid)
        self.assertEqual(candidate["matchedName"], "سروش معاصد")
        self.assertEqual(candidate["spokenName"], "سروش معاضد")

    def test_suppresses_suggestion_when_match_is_already_assigned_patient(self):
        # An implicit mention resolving to the patient already on the visit is a confirmation,
        # not a reassignment — no "reassign to <current patient>" chip (the reported bug).
        pid = uuid.uuid4()
        session = SimpleNamespace(tenant_id=uuid.uuid4(), patient_id=pid)
        fake_match = {"decision": "matched", "patientId": str(pid), "displayName": "ثریا قاسمی"}
        with patch("app.services.ai_jobs.match_patient_from_patient_information", return_value=fake_match):
            candidate = suggested_reassignment_candidate(
                object(),
                tenant_id=session.tenant_id,
                session=session,
                patient_information={"raw_mentioned_name": "ثریا قاسمی"},
            )
        self.assertIsNone(candidate)


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
        self.assertEqual(out["matchedName"], "سروش معاصد")
        self.assertEqual(out["spokenName"], "سروش معاضد")
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
