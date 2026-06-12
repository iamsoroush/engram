import unittest
import uuid
from datetime import datetime, timedelta, timezone

from app.models import Capture, CaptureStatus, CaptureType, Patient, Session, SessionStatus
from app.services.last_visit import _caption, _note_text, get_last_visit


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


def _patient() -> Patient:
    patient = Patient()
    patient.id = uuid.uuid4()
    patient.display_name = "Sara Nazari"
    return patient


def _session(when) -> Session:
    session = Session()
    session.id = uuid.uuid4()
    session.status = SessionStatus.needs_review
    session.title = "Visit"
    session.captured_at = when
    session.updated_at = when
    session.created_at = when
    return session


def _capture(capture_type, metadata, *, has_file=False) -> Capture:
    capture = Capture()
    capture.id = uuid.uuid4()
    capture.capture_type = capture_type
    capture.status = CaptureStatus.received
    capture.capture_metadata = metadata
    capture.source_artifact_id = uuid.uuid4() if has_file else None
    capture.captured_at = datetime(2026, 6, 12, tzinfo=timezone.utc)
    capture.created_at = capture.captured_at
    return capture


class NoteTextAndCaptionTests(unittest.TestCase):
    def test_note_text_reads_detail(self):
        self.assertEqual(_note_text(_capture(CaptureType.note, {"detail": "Forehead Botox, 20u."})), "Forehead Botox, 20u.")

    def test_note_text_none_when_blank(self):
        self.assertIsNone(_note_text(_capture(CaptureType.note, {"detail": "   "})))
        self.assertIsNone(_note_text(_capture(CaptureType.photo, {"original_filename": "x.png"})))

    def test_caption_reads_nested_text(self):
        self.assertEqual(_caption(_capture(CaptureType.photo, {"caption": {"text": "Before"}})), "Before")
        self.assertIsNone(_caption(_capture(CaptureType.photo, {})))


class GetLastVisitTests(unittest.TestCase):
    """AES-106/203: prior visit's note + before/after media power 'same as last time'."""

    def setUp(self):
        self.principal = _Principal()
        self.patient = _patient()

    def test_returns_prior_visit_note_and_media(self):
        newer = _session(datetime(2026, 6, 12, tzinfo=timezone.utc))
        older = _session(datetime(2026, 6, 1, tzinfo=timezone.utc))
        note = _capture(CaptureType.note, {"detail": "Forehead Botox, 20u Dysport."})
        photo = _capture(CaptureType.photo, {"caption": {"text": "Before"}}, has_file=True)
        db = _ScriptedDb(
            _Result([self.patient]),          # get_patient
            _Result([newer, older]),          # sessions
            _Result([note, photo]),           # captures for the newest session
        )
        result = get_last_visit(db, self.principal, str(self.patient.id))
        self.assertTrue(result["hasPriorVisit"])
        self.assertEqual(result["visit"]["note"], "Forehead Botox, 20u Dysport.")
        self.assertEqual(len(result["visit"]["media"]), 1)
        self.assertEqual(result["visit"]["media"][0]["caption"], "Before")
        self.assertTrue(result["visit"]["media"][0]["fileEndpoint"].endswith("/file"))
        self.assertEqual(result["sameAsLastTime"]["note"], "Forehead Botox, 20u Dysport.")
        self.assertTrue(result["sameAsLastTime"]["label"].startswith("from last visit"))

    def test_no_prior_visit_when_no_sessions(self):
        db = _ScriptedDb(_Result([self.patient]), _Result([]))
        result = get_last_visit(db, self.principal, str(self.patient.id))
        self.assertFalse(result["hasPriorVisit"])
        self.assertIsNone(result["visit"])

    def test_empty_session_shell_is_skipped(self):
        empty = _session(datetime(2026, 6, 12, tzinfo=timezone.utc))
        db = _ScriptedDb(
            _Result([self.patient]),
            _Result([empty]),
            _Result([]),  # no captures → skip this shell
        )
        result = get_last_visit(db, self.principal, str(self.patient.id))
        self.assertFalse(result["hasPriorVisit"])

    def test_media_only_visit_has_no_same_as_last_time(self):
        # A photo-only prior visit surfaces media but no note pre-fill.
        session = _session(datetime(2026, 6, 12, tzinfo=timezone.utc))
        photo = _capture(CaptureType.photo, {}, has_file=True)
        db = _ScriptedDb(_Result([self.patient]), _Result([session]), _Result([photo]))
        result = get_last_visit(db, self.principal, str(self.patient.id))
        self.assertTrue(result["hasPriorVisit"])
        self.assertIsNone(result["visit"]["note"])
        self.assertIsNone(result["sameAsLastTime"])
        self.assertEqual(len(result["visit"]["media"]), 1)


if __name__ == "__main__":
    unittest.main()
