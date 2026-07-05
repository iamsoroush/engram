"""Golden-case regression tests for the Track-E2 synthesis-apply / user-state / safety fixes.

Deterministic, DB-free where possible (pure functions + lightweight session/patient stand-ins). Each
test names the finding it locks (S-F#). The reassignment-safety and version-cache paths that need a real
DB are exercised by the e2e-stack + hermetic suites; these cover the deterministic units.
"""
import unittest
import uuid
from types import SimpleNamespace

from app.models import OrganizationSource, SessionStatus
from app.services.patient_assignment_timeline import apply_active_patient_assignment, patient_assignment_event
from app.services.synthesis_escalation import SYNTHESIS_ESCALATE_KEY
from app.services.patient_safety import (
    apply_safety_reconciliation,
    carried_rejected_safety_flag_keys,
    session_kept_safety_flags,
)
from app.services.session_processing import (
    LOW_CONFIDENCE_TREATMENT_THRESHOLD,
    process_synthesized_treatments,
)
from app.services.treatment_overlay import carried_forward_key
from app.services.ai_jobs.worker import _synthesis_output_has_body

CAP = "cap-1"
PRIOR = "prior-visit-1"


def _session(**metadata):
    return SimpleNamespace(extracted_metadata=metadata)


def _patient(flags):
    return SimpleNamespace(safety_flags=list(flags))


class _AssignResult:
    """A db.execute() result usable as both a scalar (patient lookup) and an iterable (captures loop)."""

    def __init__(self, scalar):
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return iter(())  # no captures in this session


class _AssignDb:
    def __init__(self, patients):
        self._patients = patients  # {id: patient}
        self._next_patient = None

    def set_next(self, patient):
        self._next_patient = patient

    def execute(self, _statement):
        # apply_active_patient_assignment issues: the next-patient select (scalar), then the captures
        # select (scalars). Serve the patient once, then empty capture results.
        patient, self._next_patient = self._next_patient, None
        return _AssignResult(patient)

    def get(self, _model, pk):
        return self._patients.get(pk)


class ReassignmentSafetyTests(unittest.TestCase):
    """S-F1/S-F2: the central assignment choke point drops old-patient flags, syncs the new patient,
    and invalidates wrong-patient synthesis state on a true reassignment."""

    def test_ai_reassignment_moves_safety_flags_and_invalidates(self):
        tenant_id = uuid.uuid4()
        session_id = uuid.uuid4()
        w = SimpleNamespace(id=uuid.uuid4(), tenant_id=tenant_id, safety_flags=[
            {"key": "allergy|lido", "kind": "allergy", "text": "lidocaine", "sourceSessionId": str(session_id), "sourceCaptureIds": []},
        ])
        r = SimpleNamespace(id=uuid.uuid4(), tenant_id=tenant_id, safety_flags=[])
        event = patient_assignment_event(
            source="staff", action="manually_assigned", patient_id=r.id,
            display_name="R", reason="corrected", capture_id=None,
        )
        session = SimpleNamespace(
            id=session_id, tenant_id=tenant_id, patient_id=w.id,
            status=SessionStatus.needs_review, organization_source=OrganizationSource.ai_engine,
            extracted_metadata={
                "patient_assignment_timeline": [event],
                "safety_flags": [{"kind": "allergy", "text": "lidocaine", "sourceCaptureIds": []}],
                "confirmed_carried_forward": ["cheeks|gel"],
                "report_synthesis": {"status": "current", "captureIds": [], "signature": "sig"},
            },
        )
        db = _AssignDb({w.id: w, r.id: r})
        db.set_next(r)
        apply_active_patient_assignment(db, session)

        self.assertEqual(session.patient_id, r.id)
        # S-F1: the wrong patient no longer carries this visit's flag; the correct one does.
        self.assertEqual([f for f in w.safety_flags if f.get("sourceSessionId") == str(session_id)], [])
        self.assertTrue(any(f.get("sourceSessionId") == str(session_id) for f in r.safety_flags))
        # S-F2/S-F6: wrong-patient-derived state is invalidated + a fresh escalated run is requested.
        self.assertNotIn("confirmed_carried_forward", session.extracted_metadata)
        self.assertTrue(session.extracted_metadata.get("generated_output_stale"))
        self.assertTrue(session.extracted_metadata.get(SYNTHESIS_ESCALATE_KEY))
        self.assertEqual(session.extracted_metadata["report_synthesis"]["status"], "stale")


class SafetyReconcileGuardTests(unittest.TestCase):
    """S-F6: cross-patient / cyclic reconcile decisions can never hide a distinct allergy."""

    def test_ofkey_absent_on_this_patient_downgrades_to_keep(self):
        # A decision computed against ANOTHER patient (ofKey not present here) must not hide the flag.
        patient = _patient([{"key": "allergy|x", "kind": "allergy", "text": "x"}])
        apply_safety_reconciliation(patient, {"allergy|x": {"status": "duplicate", "ofKey": "allergy|gone"}})
        self.assertNotEqual(patient.safety_flags[0].get("reconcileStatus"), "duplicate")

    def test_mutual_duplicate_cycle_keeps_one_visible(self):
        # {A: dup-of-B, B: dup-of-A} must not hide BOTH — exactly one canonical stays visible.
        patient = _patient([
            {"key": "allergy|x", "kind": "allergy", "text": "x", "addedAt": "2026-01-01"},
            {"key": "allergy|y", "kind": "allergy", "text": "y", "addedAt": "2026-01-02"},
        ])
        apply_safety_reconciliation(patient, {
            "allergy|x": {"status": "duplicate", "ofKey": "allergy|y"},
            "allergy|y": {"status": "duplicate", "ofKey": "allergy|x"},
        })
        hidden = [f for f in patient.safety_flags if f.get("reconcileStatus") == "duplicate"]
        self.assertEqual(len(hidden), 1)  # not both — the allergy survives


class RejectionCarryTests(unittest.TestCase):
    """S-F7: a rejection follows its flag across a re-synthesis that rewords the text."""

    def test_reworded_flag_stays_rejected(self):
        session = _session(
            safety_flags=[{"kind": "allergy", "text": "lidocaine sensitivity", "sourceCaptureIds": [CAP]}],
            rejected_safety_flags=["allergy|allergic to lidocaine"],  # prior key, now reworded
            rejected_safety_flag_records=[{
                "key": "allergy|allergic to lidocaine", "kind": "allergy",
                "text": "allergic to lidocaine", "sourceCaptureIds": [CAP],
            }],
        )
        carried = carried_rejected_safety_flag_keys(session)
        # The reworded flag's NEW key is now in the rejected set (same kind + shared source capture)...
        self.assertTrue(any("lidocaine sensitivity" in key for key in carried))
        # ...so it is NOT re-synced onto the patient.
        self.assertEqual(session_kept_safety_flags(session), [])

    def test_carried_forward_key_is_language_independent_when_areacode_present(self):
        # A report-language reword of `area` must not mint a new confirm-dose key when areaCode is stable.
        fa = {"areaCode": "cheeks", "area": "گونه", "product": "gel"}
        en = {"areaCode": "cheeks", "area": "cheeks", "product": "gel"}
        self.assertEqual(carried_forward_key(fa), carried_forward_key(en))


class TreatmentReviewTests(unittest.TestCase):
    """S-F11 / S-F12 / S-F14: uncertainty coding, supersede scope, and threshold unification."""

    def _treatment(self, **over):
        base = {"area": "left cheek", "product": "gel", "confidence": 0.9, "sourceCaptureIds": [CAP],
                "carriedForward": False, "attributes": {}}
        base.update(over)
        return base

    def test_prior_visit_supersede_is_accepted_not_ambiguous(self):
        # S-F12: a cross-visit correction cites a prior-visit capture (an allowed carry-forward source).
        treatments, review = process_synthesized_treatments(
            [self._treatment(supersedesCaptureId=PRIOR)],
            valid_capture_ids=[CAP], prior_visit_capture_ids=[PRIOR],
        )
        self.assertEqual(treatments[0]["supersedesCaptureId"], PRIOR)
        self.assertNotIn("ambiguous", {item["category"] for item in review})

    def test_uncertainty_code_maps_to_category(self):
        # S-F11: a coded uncertainty drives its own review category, not a blanket "ambiguous".
        _, review = process_synthesized_treatments(
            [self._treatment()], valid_capture_ids=[CAP],
            uncertainty_reasons=[{"code": "missing_lot", "text": "lot?"}],
        )
        self.assertIn("missing_lot", {item["category"] for item in review})

    def test_carried_forward_dose_uncertainty_deduped_against_keyed_item(self):
        # S-F11: a carried_forward_dose uncertainty is suppressed when the keyed carried row already covers it.
        _, review = process_synthesized_treatments(
            [self._treatment(carriedForward=True, sourceCaptureIds=[PRIOR])],
            valid_capture_ids=[CAP], prior_visit_capture_ids=[PRIOR],
            uncertainty_reasons=[{"code": "carried_forward_dose", "text": "confirm carried dose"}],
        )
        carried = [item for item in review if item["category"] == "carried_forward"]
        self.assertEqual(len(carried), 1)  # exactly ONE actionable item, not row-chip + note

    def test_low_confidence_threshold_unified_at_0_6(self):
        # S-F14: a 0.55 row (styled "low confidence" on the frontend) now also raises a review item.
        self.assertEqual(LOW_CONFIDENCE_TREATMENT_THRESHOLD, 0.6)
        _, review = process_synthesized_treatments([self._treatment(confidence=0.55)], valid_capture_ids=[CAP])
        self.assertIn("low_confidence", {item["category"] for item in review})


class HollowSynthesisTests(unittest.TestCase):
    """S-F12: a valid-but-hollow synthesis (zero blocks anywhere) is treated as malformed."""

    def test_all_empty_sections_is_hollow(self):
        output = {"sections": [{"id": "visit-summary", "blocks": []}, {"id": "treatment-performed", "blocks": []}]}
        self.assertFalse(_synthesis_output_has_body(output))

    def test_any_block_is_not_hollow(self):
        output = {"sections": [{"id": "visit-summary", "blocks": [{"type": "paragraph", "text": "x"}]}]}
        self.assertTrue(_synthesis_output_has_body(output))


if __name__ == "__main__":
    unittest.main()
