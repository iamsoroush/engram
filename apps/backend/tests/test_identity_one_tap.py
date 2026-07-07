"""One-tap E1 identity-chip endpoints (Track B fast-follow): apply-name-correction + unassign-patient.

DB-free unit tests in the suite's established style — the DB + payload + assignment choke point are
stubbed/patched so the branching (permission gates, guards, rename-in-place delegation, timeline event)
is tested in isolation. The full DB round-trip is covered by the e2e-stack + hermetic suites.
"""
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from app.services import sessions as sessions_service
from app.services.permissions import CONTRIBUTE, FULL


class _Db:
    """Minimal DB stub: the first execute() serves the assigned-patient select; commit/refresh noop."""

    def __init__(self, patient=None):
        self._patient = patient

    def execute(self, _statement):
        return SimpleNamespace(scalar_one_or_none=lambda: self._patient)

    def commit(self):
        pass

    def refresh(self, _obj):
        pass


def _principal():
    return SimpleNamespace(tenant_id=uuid.uuid4(), user_id=uuid.uuid4(), roles=frozenset({"owner"}))


def _session(patient_id):
    return SimpleNamespace(id=uuid.uuid4(), tenant_id=uuid.uuid4(), patient_id=patient_id, extracted_metadata={})


class ApplyNameCorrectionTests(unittest.TestCase):
    def _run(self, *, session, patient, perm=FULL, spoken="Sara Mohammadi", rename_result="Sara Mohammadi"):
        with patch.object(sessions_service, "get_session_for_tenant", return_value=session), patch.object(
            sessions_service, "session_permission_for_principal", return_value=perm
        ), patch.object(sessions_service, "session_payload", return_value={"ok": True}), patch.object(
            sessions_service, "audit"
        ), patch("app.services.patients.rename_patient_in_place", return_value=rename_result) as rename:
            result = sessions_service.apply_patient_name_correction(
                _Db(patient), _principal(), str(uuid.uuid4()), spoken
            )
            return result, rename

    def test_renames_the_assigned_patient_in_place(self):
        patient = SimpleNamespace(id=uuid.uuid4(), display_name="Sarah M")
        result, rename = self._run(session=_session(patient.id), patient=patient)
        self.assertEqual(result, {"ok": True})
        # The spoken name is threaded into rename_patient_in_place as the correction source.
        self.assertEqual(rename.call_args.kwargs["patient_information"], {"raw_mentioned_name": "Sara Mohammadi"})

    def test_no_assigned_patient_is_a_400(self):
        with self.assertRaises(HTTPException) as ctx:
            self._run(session=_session(None), patient=None)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_blank_spoken_name_is_a_400(self):
        patient = SimpleNamespace(id=uuid.uuid4(), display_name="Sarah M")
        with self.assertRaises(HTTPException) as ctx:
            self._run(session=_session(patient.id), patient=patient, spoken="   ")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_non_full_preset_cannot_correct(self):
        patient = SimpleNamespace(id=uuid.uuid4(), display_name="Sarah M")
        with self.assertRaises(HTTPException) as ctx:
            self._run(session=_session(patient.id), patient=patient, perm=CONTRIBUTE)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_no_effective_rename_is_a_400(self):
        patient = SimpleNamespace(id=uuid.uuid4(), display_name="Sara Mohammadi")
        with self.assertRaises(HTTPException) as ctx:
            self._run(session=_session(patient.id), patient=patient, rename_result=None)
        self.assertEqual(ctx.exception.status_code, 400)


class UnassignPatientTests(unittest.TestCase):
    def _run(self, *, session, perm=FULL):
        with patch.object(sessions_service, "get_session_for_tenant", return_value=session), patch.object(
            sessions_service, "session_permission_for_principal", return_value=perm
        ), patch.object(sessions_service, "session_payload", return_value={"ok": True}), patch.object(
            sessions_service, "audit"
        ), patch.object(sessions_service, "apply_active_patient_assignment") as apply_choke:
            result = sessions_service.unassign_session_patient(_Db(), _principal(), str(uuid.uuid4()))
            return result, session, apply_choke

    def test_unassigns_via_the_choke_point_and_appends_a_manual_unassign_event(self):
        result, session, apply_choke = self._run(session=_session(uuid.uuid4()))
        self.assertEqual(result, {"ok": True})
        apply_choke.assert_called_once()  # routed through the one assignment choke point
        timeline = session.extracted_metadata.get("patient_assignment_timeline") or []
        self.assertTrue(any(event.get("action") == "manually_unassigned" for event in timeline))

    def test_non_reassign_preset_cannot_clear_an_assigned_visit(self):
        with self.assertRaises(HTTPException) as ctx:
            self._run(session=_session(uuid.uuid4()), perm=CONTRIBUTE)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_clearing_an_already_unassigned_visit_is_allowed(self):
        # No patient to protect → the reassign gate doesn't apply even for a low preset.
        result, _sess, apply_choke = self._run(session=_session(None), perm=CONTRIBUTE)
        self.assertEqual(result, {"ok": True})
        apply_choke.assert_called_once()


if __name__ == "__main__":
    unittest.main()
