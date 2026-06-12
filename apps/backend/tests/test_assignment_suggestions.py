import unittest
import uuid
from datetime import datetime, timedelta, timezone

from app.models import Patient, Session, SessionStatus
from app.services.assignment_suggestions import suggest_session_assignment


class _Scalars:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return _Scalars(self._rows)


class _ScriptedDb:
    """Returns a pre-scripted result per ``execute`` call, in order."""

    def __init__(self, *results):
        self._results = list(results)
        self.index = 0

    def execute(self, *_args, **_kwargs):
        result = self._results[self.index]
        self.index += 1
        return result


class _Principal:
    def __init__(self):
        self.tenant_id = uuid.uuid4()
        self.user_id = uuid.uuid4()


def _session(patient_id, status, when) -> Session:
    session = Session()
    session.id = uuid.uuid4()
    session.patient_id = patient_id
    session.status = status
    session.captured_at = when
    session.updated_at = when
    session.created_at = when
    return session


def _patient(patient_id, name) -> Patient:
    patient = Patient()
    patient.id = patient_id
    patient.display_name = name
    return patient


class SuggestSessionAssignmentTests(unittest.TestCase):
    """AES-301: deterministic, rule-based assign-later suggestion (active patient, then recent)."""

    def setUp(self):
        self.principal = _Principal()
        self.now = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)

    def test_active_patient_outranks_a_more_recent_resting_patient(self):
        target = _session(None, SessionStatus.draft, self.now)
        active_pid, recent_pid = uuid.uuid4(), uuid.uuid4()
        # The resting patient's visit is newer, but the active (in-chair) patient must win.
        active_session = _session(active_pid, SessionStatus.draft, self.now - timedelta(hours=2))
        recent_session = _session(recent_pid, SessionStatus.needs_review, self.now - timedelta(minutes=5))
        db = _ScriptedDb(
            _Result([target]),
            _Result([active_session, recent_session]),
            _Result([_patient(active_pid, "Active P"), _patient(recent_pid, "Recent P")]),
        )
        result = suggest_session_assignment(db, self.principal, str(target.id))
        self.assertFalse(result["alreadyAssigned"])
        self.assertEqual(result["suggestion"]["displayName"], "Active P")
        self.assertEqual(result["suggestion"]["basis"], "active_patient")
        self.assertEqual([c["displayName"] for c in result["candidates"]], ["Active P", "Recent P"])

    def test_most_recent_patient_when_none_active(self):
        target = _session(None, SessionStatus.unassigned, self.now)
        older_pid, newer_pid = uuid.uuid4(), uuid.uuid4()
        older = _session(older_pid, SessionStatus.needs_review, self.now - timedelta(days=2))
        newer = _session(newer_pid, SessionStatus.needs_review, self.now - timedelta(hours=1))
        db = _ScriptedDb(
            _Result([target]),
            _Result([older, newer]),
            _Result([_patient(older_pid, "Older P"), _patient(newer_pid, "Newer P")]),
        )
        result = suggest_session_assignment(db, self.principal, str(target.id))
        self.assertEqual(result["suggestion"]["displayName"], "Newer P")
        self.assertEqual(result["suggestion"]["basis"], "recent_patient")

    def test_already_assigned_session_has_no_suggestion(self):
        target = _session(uuid.uuid4(), SessionStatus.needs_review, self.now)
        db = _ScriptedDb(_Result([target]))
        result = suggest_session_assignment(db, self.principal, str(target.id))
        self.assertTrue(result["alreadyAssigned"])
        self.assertIsNone(result["suggestion"])

    def test_no_prior_patients_yields_no_suggestion(self):
        target = _session(None, SessionStatus.unassigned, self.now)
        db = _ScriptedDb(_Result([target]), _Result([]))
        result = suggest_session_assignment(db, self.principal, str(target.id))
        self.assertIsNone(result["suggestion"])
        self.assertEqual(result["candidates"], [])


if __name__ == "__main__":
    unittest.main()
