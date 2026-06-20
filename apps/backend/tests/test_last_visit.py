import unittest
import uuid
from datetime import datetime, timedelta, timezone

from app.models import Capture, CaptureStatus, CaptureType, Patient, Session, SessionStatus
from app.services.last_visit import (
    MAX_RECENT_VISITS,
    _caption,
    _note_text,
    get_last_visit,
    get_session_context,
)


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

    def test_digest_includes_playable_voice_memos(self):
        # The digest counts (and exposes as playable) the prior visit's voice memos.
        session = _session(datetime(2026, 6, 12, tzinfo=timezone.utc))
        note = _capture(CaptureType.note, {"detail": "Filler cheeks."})
        audio_one = _capture(CaptureType.audio, {}, has_file=True)
        audio_two = _capture(CaptureType.audio, {}, has_file=True)
        photo = _capture(CaptureType.photo, {}, has_file=True)
        db = _ScriptedDb(_Result([self.patient]), _Result([session]), _Result([note, audio_one, audio_two, photo]))
        result = get_last_visit(db, self.principal, str(self.patient.id))
        self.assertEqual(result["visit"]["audioCount"], 2)
        self.assertEqual(len(result["visit"]["audio"]), 2)
        self.assertTrue(result["visit"]["audio"][0]["contentEndpoint"].endswith("/file-content"))
        self.assertEqual(len(result["visit"]["media"]), 1)  # audio is not in the photo strip


class GetSessionContextTests(unittest.TestCase):
    """Deterministic session context: last-visit digest + cross-visit photo strip + ordinal + key facts."""

    def setUp(self):
        self.principal = _Principal()
        self.patient = _patient()

    def _photo(self):
        return _capture(CaptureType.photo, {}, has_file=True)

    def test_digest_strip_ordinal_and_key_facts(self):
        self.patient.notes = "  Allergic to lidocaine  "
        newer = _session(datetime(2026, 6, 12, tzinfo=timezone.utc))
        older = _session(datetime(2026, 6, 1, tzinfo=timezone.utc))
        note = _capture(CaptureType.note, {"detail": "Forehead Botox, 20u."})
        newer_caps = [note, self._photo(), self._photo()]
        older_caps = [self._photo()]
        db = _ScriptedDb(
            _Result([self.patient]),   # get_patient (session-context)
            _Result([self.patient]),   # get_patient (inside get_last_visit)
            _Result([newer, older]),   # sessions (get_last_visit)
            _Result(newer_caps),       # captures for newer (get_last_visit) → the digest
            _Result([newer, older]),   # sessions (session-context)
            _Result(newer_caps),       # captures for newer (session-context)
            _Result(older_caps),       # captures for older (session-context)
        )
        result = get_session_context(db, self.principal, str(self.patient.id))
        self.assertEqual(result["lastVisit"]["visit"]["note"], "Forehead Botox, 20u.")
        self.assertEqual(len(result["recentVisits"]), 2)
        self.assertEqual(result["recentVisits"][0]["photoCount"], 2)
        self.assertEqual(result["recentVisits"][1]["photoCount"], 1)
        self.assertEqual(result["totalPriorVisits"], 2)
        self.assertEqual(result["visitOrdinal"], 3)  # the in-progress visit is the 3rd
        self.assertEqual(result["keyFacts"], "Allergic to lidocaine")  # trimmed

    def test_note_only_visit_excluded_from_strip_but_counts(self):
        session = _session(datetime(2026, 6, 12, tzinfo=timezone.utc))
        note = _capture(CaptureType.note, {"detail": "Consult only."})
        db = _ScriptedDb(
            _Result([self.patient]),   # get_patient (session-context)
            _Result([self.patient]),   # get_patient (get_last_visit)
            _Result([session]),        # sessions (get_last_visit)
            _Result([note]),           # captures (get_last_visit)
            _Result([session]),        # sessions (session-context)
            _Result([note]),           # captures (session-context) → no photos → not in strip
        )
        result = get_session_context(db, self.principal, str(self.patient.id))
        self.assertTrue(result["lastVisit"]["hasPriorVisit"])
        self.assertEqual(result["recentVisits"], [])
        self.assertEqual(result["totalPriorVisits"], 1)
        self.assertEqual(result["visitOrdinal"], 2)
        self.assertIsNone(result["keyFacts"])

    def test_no_prior_visits_first_time_patient(self):
        db = _ScriptedDb(
            _Result([self.patient]),   # get_patient (session-context)
            _Result([self.patient]),   # get_patient (get_last_visit)
            _Result([]),               # sessions (get_last_visit) → none
            _Result([]),               # sessions (session-context) → none
        )
        result = get_session_context(db, self.principal, str(self.patient.id))
        self.assertFalse(result["lastVisit"]["hasPriorVisit"])
        self.assertEqual(result["recentVisits"], [])
        self.assertEqual(result["totalPriorVisits"], 0)
        self.assertEqual(result["visitOrdinal"], 1)

    def test_recent_visits_bounded_but_total_counts_all(self):
        count = MAX_RECENT_VISITS + 2
        sessions = [_session(datetime(2026, 6, 12, tzinfo=timezone.utc) - timedelta(days=i)) for i in range(count)]
        results = [
            _Result([self.patient]),       # get_patient (session-context)
            _Result([self.patient]),       # get_patient (get_last_visit)
            _Result(list(sessions)),       # sessions (get_last_visit)
            _Result([self._photo()]),      # captures for newest (get_last_visit)
            _Result(list(sessions)),       # sessions (session-context)
        ]
        results += [_Result([self._photo()]) for _ in range(count)]  # captures per session (session-context)
        result = get_session_context(_ScriptedDb(*results), self.principal, str(self.patient.id))
        self.assertEqual(result["totalPriorVisits"], count)
        self.assertEqual(len(result["recentVisits"]), MAX_RECENT_VISITS)  # strip is bounded
        self.assertEqual(result["visitOrdinal"], count + 1)


if __name__ == "__main__":
    unittest.main()
