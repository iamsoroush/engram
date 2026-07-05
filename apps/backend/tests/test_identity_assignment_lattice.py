"""Decision-lattice + INV-SILENT tests for the capture identity/assignment resolver (Track E1).

Exercises ``_resolve_capture_identity`` across the full lattice — first-identity-wins, dead-zone
create+assign, same-patient name correction, explicit/policy-gated reassignment, detach, OOC-veto,
and A-F7 inert assignment — asserting the never-silent invariant: a confident detection or an
explicit instruction always ends in an applied effect, a visible suggestion, or a visible notice.
Collaborators that touch the DB are patched so the branching logic is tested in isolation.
"""
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from app.models import PatientStatus
from app.services.ai_jobs import worker


def _patient(name, *, ai_created=False):
    return SimpleNamespace(
        id=uuid.uuid4(), display_name=name, tenant_id=None, status=PatientStatus.active,
        notes="Created by AI from an audio capture. Complete and verify patient details." if ai_created else None,
    )


class _FakeDb:
    """A DB stub whose ``get`` resolves patients by id; ``execute`` is unused (collaborators patched)."""

    def __init__(self, patients=None):
        self._patients = {str(p.id): p for p in (patients or [])}

    def get(self, _model, ident):
        return self._patients.get(str(ident))

    def execute(self, _statement):  # pragma: no cover - collaborators are patched in these tests
        return SimpleNamespace(scalar_one_or_none=lambda: None)


def _output(patient_information=None, *, assignment=None, detach=None, out_of_context=None):
    intents = {}
    if assignment is not None:
        intents["assignment"] = {"present": True, "basis": assignment}
    if detach is not None:
        intents["detach"] = {"present": True, "basis": detach}
    if out_of_context is not None:
        intents["out_of_context"] = {"present": True, "confidence": 0.9, "reason": out_of_context}
    return {"patient_information": patient_information, "intents": intents}


def _match(decision, *, patient_id=None, display_name=None, confidence=1.0, candidate_set=None):
    return {
        "schemaVersion": "2026-06-02.patient-match-candidate.v1",
        "decision": decision, "status": decision,
        "patientId": str(patient_id) if patient_id else None,
        "displayName": display_name,
        "candidateSet": candidate_set if candidate_set is not None else (
            [{"patientId": str(patient_id), "displayName": display_name, "confidence": confidence}] if patient_id else []
        ),
        "risks": [],
    }


class IdentityLatticeTests(unittest.TestCase):
    def setUp(self):
        self.job = SimpleNamespace(id=uuid.uuid4(), tenant_id=uuid.uuid4(), created_by_user_id=uuid.uuid4())
        self.capture = SimpleNamespace(id=uuid.uuid4(), created_by_user_id=uuid.uuid4(), captured_at=None, created_at=None)

    def _session(self, patient_id=None):
        return SimpleNamespace(id=uuid.uuid4(), tenant_id=self.job.tenant_id, patient_id=patient_id, extracted_metadata={})

    # --- Unassigned: first-identity-wins ------------------------------------------------------
    def test_unassigned_exact_match_assigns(self):
        target = _patient("Maryam Hosseini")
        session = self._session(patient_id=None)
        db = _FakeDb([target])
        with (
            patch.object(worker.ai_jobs_pkg, "match_patient_from_patient_information", return_value=_match("matched", patient_id=target.id, display_name=target.display_name)),
            patch.object(worker, "resolve_ai_patient_from_match", return_value=(target, False)),
            patch.object(worker, "assign_session_to_ai_patient", return_value=True) as assign,
        ):
            candidate, action = worker._resolve_capture_identity(
                db, job=self.job, session=session, capture=self.capture,
                output=_output({"raw_mentioned_name": "Maryam Hosseini"}, assignment="implicit"), strictness="balanced",
            )
        assign.assert_called_once()
        self.assertIsNotNone(action)
        self.assertEqual(action["action"], "matched_and_assigned")

    def test_unassigned_no_match_creates_and_assigns(self):
        created = _patient("Sara Ahmadi", ai_created=True)
        session = self._session(patient_id=None)
        db = _FakeDb([created])
        with (
            patch.object(worker.ai_jobs_pkg, "match_patient_from_patient_information", return_value=_match("no_match")),
            patch.object(worker, "fuzzy_auto_apply_candidate", return_value=None),
            patch.object(worker, "near_match_suggestion", return_value=None),
            patch.object(worker, "find_patient_duplicates", return_value={"hasLikelyDuplicate": False, "candidates": []}),
            patch.object(worker, "create_patient_from_patient_information", return_value=created),
            patch.object(worker, "assign_session_to_ai_patient", return_value=True),
        ):
            candidate, action = worker._resolve_capture_identity(
                db, job=self.job, session=session, capture=self.capture,
                output=_output({"raw_mentioned_name": "Sara Ahmadi"}, assignment="implicit"), strictness="balanced",
            )
        self.assertIsNotNone(action)
        self.assertTrue(action["created"])

    def test_unassigned_dead_zone_creates_with_similar_note(self):
        # Sub-threshold possible_match (the 0.762 dead zone): no auto-apply, no dominant near-match →
        # create + assign the spoken patient, keeping the look-alike as an informational note (Fix 7).
        created = _patient("سروش معاضد", ai_created=True)
        session = self._session(patient_id=None)
        db = _FakeDb([created])
        near_miss = _match("possible_match", patient_id=uuid.uuid4(), display_name="سورنا معاضد", confidence=0.70)
        with (
            patch.object(worker.ai_jobs_pkg, "match_patient_from_patient_information", return_value=near_miss),
            patch.object(worker, "resolve_ai_patient_from_match", return_value=(None, False)),
            patch.object(worker, "fuzzy_auto_apply_candidate", return_value=None),
            patch.object(worker, "near_match_suggestion", return_value=None),
            patch.object(worker, "find_patient_duplicates", return_value={"hasLikelyDuplicate": False, "candidates": []}),
            patch.object(worker, "create_patient_from_patient_information", return_value=created),
            patch.object(worker, "assign_session_to_ai_patient", return_value=True),
        ):
            candidate, action = worker._resolve_capture_identity(
                db, job=self.job, session=session, capture=self.capture,
                output=_output({"raw_mentioned_name": "سروش معاضد"}, assignment="implicit"), strictness="balanced",
            )
        self.assertIsNotNone(action)
        self.assertTrue(action["created"])
        self.assertIn("similarExisting", action)

    def test_unassigned_strong_duplicate_suggests_instead_of_create(self):
        # A-F16: AI creation runs the duplicate guard; a strong hit suggests use-existing, never creates.
        existing_id = uuid.uuid4()
        session = self._session(patient_id=None)
        with (
            patch.object(worker.ai_jobs_pkg, "match_patient_from_patient_information", return_value=_match("no_match")),
            patch.object(worker, "resolve_ai_patient_from_match", return_value=(None, False)),
            patch.object(worker, "fuzzy_auto_apply_candidate", return_value=None),
            patch.object(worker, "near_match_suggestion", return_value=None),
            patch.object(worker, "find_patient_duplicates", return_value={
                "hasLikelyDuplicate": True,
                "candidates": [{"patientId": str(existing_id), "displayName": "Maryam", "confidence": 0.97}],
            }),
            patch.object(worker, "create_patient_from_patient_information") as create,
            patch.object(worker, "assign_session_to_ai_patient") as assign,
        ):
            candidate, action = worker._resolve_capture_identity(
                db=_FakeDb(), job=self.job, session=session, capture=self.capture,
                output=_output({"raw_mentioned_name": "Maryam"}, assignment="implicit"), strictness="balanced",
            )
        create.assert_not_called()
        assign.assert_not_called()
        self.assertIsNone(action)
        self.assertEqual(candidate["status"], "suggested_reassignment")
        self.assertTrue(candidate["duplicateGuard"])

    # --- Assigned: reassignment + policy --------------------------------------------------------
    def test_assigned_explicit_reassign_to_other_permitted_applies(self):
        current = _patient("Ali")
        other = _patient("Maryam")
        session = self._session(patient_id=current.id)
        db = _FakeDb([current, other])
        with (
            patch.object(worker.ai_jobs_pkg, "match_patient_from_patient_information", return_value=_match("matched", patient_id=other.id, display_name=other.display_name)),
            patch.object(worker, "user_can_reassign_session", return_value=True),
            patch.object(worker, "spoken_name_matches_patient", return_value=False),
            patch.object(worker, "resolve_ai_patient_from_match", return_value=(other, False)),
            patch.object(worker, "assign_session_to_ai_patient", return_value=True),
        ):
            candidate, action = worker._resolve_capture_identity(
                db, job=self.job, session=session, capture=self.capture,
                output=_output({"raw_mentioned_name": "Maryam"}, assignment="explicit"), strictness="balanced",
            )
        self.assertIsNotNone(action)

    def test_assigned_explicit_reassign_not_permitted_is_policy_deferred_suggestion(self):
        current = _patient("Ali")
        session = self._session(patient_id=current.id)
        db = _FakeDb([current])
        with (
            patch.object(worker.ai_jobs_pkg, "match_patient_from_patient_information", return_value=_match("matched", patient_id=uuid.uuid4(), display_name="Maryam")),
            patch.object(worker, "user_can_reassign_session", return_value=False),
            patch.object(worker, "spoken_name_matches_patient", return_value=False),
        ):
            candidate, action = worker._resolve_capture_identity(
                db, job=self.job, session=session, capture=self.capture,
                output=_output({"raw_mentioned_name": "Maryam"}, assignment="explicit"), strictness="balanced",
            )
        self.assertIsNone(action)
        self.assertIsNotNone(candidate)
        self.assertTrue(candidate.get("policyDeferred"))

    def test_assigned_explicit_no_match_uncreatable_yields_notice(self):
        # A-F12: explicit reassignment that resolves to no applicable patient → actionable notice.
        current = _patient("Ali")
        session = self._session(patient_id=current.id)
        db = _FakeDb([current])
        with (
            patch.object(worker.ai_jobs_pkg, "match_patient_from_patient_information", return_value=_match("no_match")),
            patch.object(worker, "user_can_reassign_session", return_value=True),
            patch.object(worker, "spoken_name_matches_patient", return_value=False),
            patch.object(worker, "fuzzy_auto_apply_candidate", return_value=None),
            patch.object(worker, "near_match_suggestion", return_value=None),
            patch.object(worker, "find_patient_duplicates", return_value={"hasLikelyDuplicate": False, "candidates": []}),
            patch.object(worker, "create_patient_from_patient_information", return_value=None),  # uncreatable (phone-only)
        ):
            candidate, action = worker._resolve_capture_identity(
                db, job=self.job, session=session, capture=self.capture,
                output=_output({"phone": "09120000000"}, assignment="explicit"), strictness="balanced",
            )
        self.assertIsNone(action)
        self.assertEqual(candidate["status"], "assignment_no_effect")

    # --- Same-patient name correction (Fix 1) --------------------------------------------------
    def test_assigned_explicit_correction_of_ai_patient_renames_in_place(self):
        current = _patient("سورنا معاضد", ai_created=True)
        session = self._session(patient_id=current.id)
        db = _FakeDb([current])
        with (
            patch.object(worker.ai_jobs_pkg, "match_patient_from_patient_information", return_value=_match("possible_match", patient_id=current.id, display_name=current.display_name, confidence=0.8)),
            patch.object(worker, "user_can_reassign_session", return_value=True),
            patch.object(worker, "spoken_name_matches_patient", return_value=False),
            patch.object(worker, "rename_patient_in_place", return_value="سروش معاضد") as rename,
        ):
            candidate, action = worker._resolve_capture_identity(
                db, job=self.job, session=session, capture=self.capture,
                output=_output({"raw_mentioned_name": "سروش معاضد"}, assignment="explicit"), strictness="balanced",
            )
        rename.assert_called_once()
        self.assertEqual(candidate["status"], "name_corrected")
        self.assertEqual(action["action"], "renamed")

    def test_assigned_implicit_correction_is_suggestion(self):
        current = _patient("سورنا معاضد", ai_created=True)
        session = self._session(patient_id=current.id)
        db = _FakeDb([current])
        with (
            patch.object(worker.ai_jobs_pkg, "match_patient_from_patient_information", return_value=_match("possible_match", patient_id=current.id, display_name=current.display_name, confidence=0.8)),
            patch.object(worker, "user_can_reassign_session", return_value=True),
            patch.object(worker, "spoken_name_matches_patient", return_value=False),
            patch.object(worker, "rename_patient_in_place") as rename,
        ):
            candidate, action = worker._resolve_capture_identity(
                db, job=self.job, session=session, capture=self.capture,
                output=_output({"raw_mentioned_name": "سروش معاضد"}, assignment="implicit"), strictness="balanced",
            )
        rename.assert_not_called()
        self.assertIsNone(action)
        self.assertEqual(candidate["status"], "suggested_name_correction")

    def test_assigned_echo_of_same_patient_is_silent(self):
        # A bare mention of the already-assigned patient (name matches) is a genuine echo — no chip,
        # no notice, and NOT an INV-SILENT violation.
        current = _patient("Maryam")
        session = self._session(patient_id=current.id)
        db = _FakeDb([current])
        with (
            patch.object(worker.ai_jobs_pkg, "match_patient_from_patient_information", return_value=_match("matched", patient_id=current.id, display_name="Maryam")),
            patch.object(worker, "user_can_reassign_session", return_value=True),
            patch.object(worker, "spoken_name_matches_patient", return_value=True),
            patch.object(worker, "suggested_reassignment_candidate", return_value=None),
        ):
            candidate, action = worker._resolve_capture_identity(
                db, job=self.job, session=session, capture=self.capture,
                output=_output({"raw_mentioned_name": "Maryam"}, assignment="implicit"), strictness="balanced",
            )
        self.assertIsNone(candidate)
        self.assertIsNone(action)

    # --- Detach (A-F9) --------------------------------------------------------------------------
    def test_detach_on_assigned_visit_suggests_unassign(self):
        current = _patient("Maryam")
        session = self._session(patient_id=current.id)
        db = _FakeDb([current])
        candidate, action = worker._resolve_capture_identity(
            db, job=self.job, session=session, capture=self.capture,
            output=_output(None, detach="explicit"), strictness="balanced",
        )
        self.assertIsNone(action)
        self.assertEqual(candidate["status"], "suggested_unassign")

    # --- OOC veto (A-F4) ------------------------------------------------------------------------
    def test_out_of_context_identity_is_downgraded_to_suggestion(self):
        session = self._session(patient_id=None)
        with patch.object(
            worker.ai_jobs_pkg, "match_patient_from_patient_information", return_value=_match("no_match")
        ), patch.object(worker, "assign_session_to_ai_patient") as assign, patch.object(
            worker, "create_patient_from_patient_information"
        ) as create:
            candidate, action = worker._resolve_capture_identity(
                _FakeDb(), job=self.job, session=session, capture=self.capture,
                output=_output({"raw_mentioned_name": "Karimi"}, assignment="implicit", out_of_context="reminder to call"),
                strictness="balanced",
            )
        assign.assert_not_called()
        create.assert_not_called()
        self.assertIsNone(action)
        self.assertTrue(candidate["outOfContext"])

    # --- A-F7 inert assignment ------------------------------------------------------------------
    def test_inert_assignment_surfaces_conflict(self):
        target = _patient("Sara")
        session = self._session(patient_id=None)
        db = _FakeDb([target])
        with (
            patch.object(worker.ai_jobs_pkg, "match_patient_from_patient_information", return_value=_match("matched", patient_id=target.id, display_name="Sara")),
            patch.object(worker, "resolve_ai_patient_from_match", return_value=(target, False)),
            patch.object(worker, "assign_session_to_ai_patient", return_value=False),  # did not become active
            patch.object(worker, "active_patient_assignment_event", return_value={"patientId": str(uuid.uuid4()), "displayName": "Maryam"}),
        ):
            candidate, action = worker._resolve_capture_identity(
                db, job=self.job, session=session, capture=self.capture,
                output=_output({"raw_mentioned_name": "Sara"}, assignment="implicit"), strictness="balanced",
            )
        self.assertIsNone(action)
        self.assertTrue(candidate["inertAssignment"])


class ExplicitInstructionUnsatisfiedTests(unittest.TestCase):
    """The INV-SILENT completion backstop predicate."""

    def setUp(self):
        self.job = SimpleNamespace(id=uuid.uuid4(), tenant_id=uuid.uuid4(), created_by_user_id=uuid.uuid4())

    def test_detach_on_assigned_is_unsatisfied(self):
        session = SimpleNamespace(patient_id=uuid.uuid4(), tenant_id=self.job.tenant_id)
        self.assertTrue(worker._explicit_instruction_unsatisfied(_FakeDb(), job=self.job, session=session, output=_output(None, detach="explicit")))

    def test_detach_on_unassigned_is_satisfied(self):
        session = SimpleNamespace(patient_id=None, tenant_id=self.job.tenant_id)
        self.assertFalse(worker._explicit_instruction_unsatisfied(_FakeDb(), job=self.job, session=session, output=_output(None, detach="explicit")))

    def test_implicit_mention_is_not_a_violation(self):
        session = SimpleNamespace(patient_id=uuid.uuid4(), tenant_id=self.job.tenant_id)
        self.assertFalse(worker._explicit_instruction_unsatisfied(_FakeDb(), job=self.job, session=session, output=_output({"raw_mentioned_name": "X"}, assignment="implicit")))

    def test_explicit_echo_is_satisfied(self):
        pid = uuid.uuid4()
        session = SimpleNamespace(patient_id=pid, tenant_id=self.job.tenant_id)
        with (
            patch.object(worker.ai_jobs_pkg, "match_patient_from_patient_information", return_value=_match("matched", patient_id=pid, display_name="X")),
            patch.object(worker, "spoken_name_matches_patient", return_value=True),
        ):
            self.assertFalse(worker._explicit_instruction_unsatisfied(_FakeDb(), job=self.job, session=session, output=_output({"raw_mentioned_name": "X"}, assignment="explicit")))

    def test_explicit_to_other_patient_is_unsatisfied(self):
        session = SimpleNamespace(patient_id=uuid.uuid4(), tenant_id=self.job.tenant_id)
        with (
            patch.object(worker.ai_jobs_pkg, "match_patient_from_patient_information", return_value=_match("matched", patient_id=uuid.uuid4(), display_name="Y")),
            patch.object(worker, "spoken_name_matches_patient", return_value=False),
        ):
            self.assertTrue(worker._explicit_instruction_unsatisfied(_FakeDb(), job=self.job, session=session, output=_output({"raw_mentioned_name": "Y"}, assignment="explicit")))


if __name__ == "__main__":
    unittest.main()
