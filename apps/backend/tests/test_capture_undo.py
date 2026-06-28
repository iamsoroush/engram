import unittest
import uuid

from app.models import Capture, Patient, PatientStatus, Session
from app.services.captures import (
    _archive_orphaned_ai_patient,
    _patient_created_by_capture,
    can_remove_capture,
)
from app.services.patients import AI_CREATED_PATIENT_NOTE


class _Principal:
    def __init__(self, tenant_id, user_id):
        self.tenant_id = tenant_id
        self.user_id = user_id


class _Result:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _ScriptedDb:
    """Minimal DB double: get() → the patient; execute() → scripted (has_session, has_capture)."""

    def __init__(self, patient, results):
        self._patient = patient
        self._results = list(results)
        self._i = 0
        self.added = []

    def get(self, _model, _pk):
        return self._patient

    def execute(self, *_a, **_k):
        result = _Result(self._results[self._i])
        self._i += 1
        return result

    def add(self, obj):
        self.added.append(obj)


def _session(owner_id, timeline=None):
    s = Session()
    s.id = uuid.uuid4()
    s.created_by_user_id = owner_id
    s.extracted_metadata = {"patient_assignment_timeline": timeline or []}
    return s


def _ai_patient(tenant_id):
    p = Patient()
    p.id = uuid.uuid4()
    p.tenant_id = tenant_id
    p.display_name = "AI نمونه"
    p.notes = AI_CREATED_PATIENT_NOTE
    p.status = PatientStatus.active
    return p


class RemovalPolicyTests(unittest.TestCase):
    def test_owner_only_even_for_admin(self):
        owner = uuid.uuid4()
        s = _session(owner)
        self.assertTrue(can_remove_capture(s, _Principal(uuid.uuid4(), owner)))
        # A different user (even an admin) is NOT the owner → cannot remove.
        self.assertFalse(can_remove_capture(s, _Principal(uuid.uuid4(), uuid.uuid4())))


class CreatedByCaptureTests(unittest.TestCase):
    def test_finds_patient_created_by_this_capture(self):
        cap = uuid.uuid4()
        pid = uuid.uuid4()
        s = _session(uuid.uuid4(), [{"captureId": str(cap), "created": True, "patientId": str(pid)}])
        self.assertEqual(_patient_created_by_capture(s, cap), pid)

    def test_ignores_non_created_or_other_capture(self):
        cap = uuid.uuid4()
        s = _session(uuid.uuid4(), [
            {"captureId": str(cap), "created": False, "patientId": str(uuid.uuid4())},  # matched, not created
            {"captureId": str(uuid.uuid4()), "created": True, "patientId": str(uuid.uuid4())},  # other capture
        ])
        self.assertIsNone(_patient_created_by_capture(s, cap))


class ArchiveOrphanedAiPatientTests(unittest.TestCase):
    def _principal(self, tenant):
        return _Principal(tenant, uuid.uuid4())

    def test_archives_unverified_ai_orphan(self):
        tenant = uuid.uuid4()
        p = _ai_patient(tenant)
        db = _ScriptedDb(p, results=[None, None])  # no dependent session, no live capture
        archived = _archive_orphaned_ai_patient(db, self._principal(tenant), p.id)
        self.assertTrue(archived)
        self.assertEqual(p.status, PatientStatus.archived)
        self.assertTrue(db.added)  # audit + feedback staged

    def test_skips_when_has_dependent_session(self):
        tenant = uuid.uuid4()
        p = _ai_patient(tenant)
        db = _ScriptedDb(p, results=[uuid.uuid4(), None])  # a session still references it
        self.assertFalse(_archive_orphaned_ai_patient(db, self._principal(tenant), p.id))
        self.assertEqual(p.status, PatientStatus.active)

    def test_skips_non_ai_created_patient(self):
        tenant = uuid.uuid4()
        p = _ai_patient(tenant)
        p.notes = "Real patient, verified."  # not the AI-creation breadcrumb
        db = _ScriptedDb(p, results=[None, None])
        self.assertFalse(_archive_orphaned_ai_patient(db, self._principal(tenant), p.id))
        self.assertEqual(p.status, PatientStatus.active)

    def test_noop_on_none(self):
        self.assertFalse(_archive_orphaned_ai_patient(_ScriptedDb(None, []), self._principal(uuid.uuid4()), None))


if __name__ == "__main__":
    unittest.main()
