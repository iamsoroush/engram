import unittest
import uuid
from types import SimpleNamespace

from app.services import caseload


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDb:
    """Returns queued scalar values in order — first the tenant vertical, then later lookups."""

    def __init__(self, values):
        self._values = list(values)

    def execute(self, _statement):
        value = self._values.pop(0) if self._values else None
        return _FakeResult(value)


def _principal(user_id=None, tenant_id=None):
    uid = user_id or uuid.uuid4()
    tid = tenant_id or uuid.uuid4()
    return SimpleNamespace(user_id=uid, tenant_id=tid, user=SimpleNamespace(id=uid))


class FederatedTenantTests(unittest.TestCase):
    def test_therapy_is_federated_aesthetics_is_not(self):
        self.assertTrue(caseload.is_federated_caseload(_FakeDb(["therapy"]), uuid.uuid4()))
        self.assertFalse(caseload.is_federated_caseload(_FakeDb(["aesthetics"]), uuid.uuid4()))
        # Legacy 'clinic' normalizes to aesthetics → shared workspace.
        self.assertFalse(caseload.is_federated_caseload(_FakeDb(["clinic"]), uuid.uuid4()))
        # Missing vertical defaults to aesthetics.
        self.assertFalse(caseload.is_federated_caseload(_FakeDb([None]), uuid.uuid4()))


class CaseloadConditionTests(unittest.TestCase):
    def test_no_condition_for_shared_workspace(self):
        self.assertIsNone(caseload.caseload_patient_condition(_FakeDb(["aesthetics"]), _principal()))

    def test_condition_present_for_therapy(self):
        condition = caseload.caseload_patient_condition(_FakeDb(["therapy"]), _principal())
        self.assertIsNotNone(condition)  # a SQLAlchemy OR-condition restricting Patient rows


class PatientInCaseloadTests(unittest.TestCase):
    def test_shared_workspace_always_in_caseload(self):
        principal = _principal()
        other_owner = SimpleNamespace(id=uuid.uuid4(), created_by_user_id=uuid.uuid4())
        self.assertTrue(caseload.patient_in_caseload(_FakeDb(["aesthetics"]), principal, other_owner))

    def test_therapy_owner_is_in_caseload(self):
        principal = _principal()
        owned = SimpleNamespace(id=uuid.uuid4(), created_by_user_id=principal.user_id)
        # Only the vertical lookup is needed — ownership short-circuits before the session query.
        self.assertTrue(caseload.patient_in_caseload(_FakeDb(["therapy"]), principal, owned))

    def test_therapy_non_owner_without_session_is_excluded(self):
        principal = _principal()
        foreign = SimpleNamespace(id=uuid.uuid4(), created_by_user_id=uuid.uuid4())
        # vertical → 'therapy', then the owned-session lookup → None (no session).
        self.assertFalse(caseload.patient_in_caseload(_FakeDb(["therapy", None]), principal, foreign))

    def test_therapy_non_owner_with_owned_session_is_included(self):
        principal = _principal()
        foreign = SimpleNamespace(id=uuid.uuid4(), created_by_user_id=uuid.uuid4())
        # vertical → 'therapy', then the owned-session lookup returns a session id.
        self.assertTrue(caseload.patient_in_caseload(_FakeDb(["therapy", uuid.uuid4()]), principal, foreign))


if __name__ == "__main__":
    unittest.main()
