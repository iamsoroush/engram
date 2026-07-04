import unittest
import uuid
from datetime import datetime, timezone

from app.models import Capture, CaptureStatus, CaptureType, Session, SessionReportVersion
from app.services.report_versions import (
    record_report_version,
    restore_report_version,
    session_capture_set,
)


class _Scalars:
    def __init__(self, rows):
        self._rows = list(rows)

    def __iter__(self):
        return iter(self._rows)

    def all(self):
        return list(self._rows)


class _Result:
    def __init__(self, *, scalar=None, scalars=None):
        self._scalar = scalar
        self._scalars = scalars or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return _Scalars(self._scalars)


class _Db:
    """Scripted DB: execute() returns the next queued _Result; add() collects staged rows."""

    def __init__(self, results):
        self._results = list(results)
        self._i = 0
        self.added = []

    def execute(self, *_a, **_k):
        result = self._results[self._i]
        self._i += 1
        return result

    def add(self, obj):
        self.added.append(obj)


def _session():
    s = Session()
    s.id = uuid.uuid4()
    s.tenant_id = uuid.uuid4()
    s.summary = "old"
    s.generated_report = "old report"
    s.extracted_metadata = {}
    return s


def _cap(session, text, *, minute=0):
    c = Capture()
    c.id = uuid.uuid4()
    c.tenant_id = session.tenant_id
    c.session_id = session.id
    c.status = CaptureStatus.processed
    c.capture_type = CaptureType.note
    c.captured_at = datetime(2026, 6, 28, 12, minute, tzinfo=timezone.utc)
    c.created_at = c.captured_at
    c.capture_metadata = {"detail": text}
    return c


class CaptureSetHashTests(unittest.TestCase):
    def test_deterministic_and_order_independent_input(self):
        s = _session()
        c1, c2 = _cap(s, "alpha", minute=1), _cap(s, "beta", minute=2)
        h1, items1 = session_capture_set(_Db([_Result(scalars=[c1, c2])]), s)
        # Same captures fed in a different DB order → same hash (we sort canonically).
        h2, items2 = session_capture_set(_Db([_Result(scalars=[c2, c1])]), s)
        self.assertEqual(h1, h2)
        self.assertEqual(len(items1), 2)

    def test_hash_changes_when_a_capture_is_removed(self):
        s = _session()
        c1, c2 = _cap(s, "alpha", minute=1), _cap(s, "beta", minute=2)
        full, _ = session_capture_set(_Db([_Result(scalars=[c1, c2])]), s)
        without_c2, _ = session_capture_set(_Db([_Result(scalars=[c1])]), s)
        self.assertNotEqual(full, without_c2)

    def test_hash_changes_when_content_edited(self):
        s = _session()
        c1 = _cap(s, "alpha", minute=1)
        before, _ = session_capture_set(_Db([_Result(scalars=[c1])]), s)
        c1.capture_metadata = {"detail": "alpha EDITED"}
        after, _ = session_capture_set(_Db([_Result(scalars=[c1])]), s)
        self.assertNotEqual(before, after)

    def test_hash_changes_when_marked_out_of_context(self):
        # Out-of-context membership is part of the key (D1): a mark-relevant / mark-out-of-context
        # toggle changes the synthesized input, so cache-hit-before-dispatch must not collide the two.
        s = _session()
        c1 = _cap(s, "alpha", minute=1)
        in_context, items = session_capture_set(_Db([_Result(scalars=[c1])]), s)
        self.assertIs(items[0]["outOfContext"], False)
        c1.capture_metadata = {**c1.capture_metadata, "out_of_context": {"present": True}}
        out_of_context, _ = session_capture_set(_Db([_Result(scalars=[c1])]), s)
        self.assertNotEqual(in_context, out_of_context)


class RecordTests(unittest.TestCase):
    def test_records_a_new_version(self):
        s = _session()
        s.extracted_metadata = {"treatments": [{"area": "lip"}], "safety_flags": [], "rejected_safety_flags": ["x"]}
        c1 = _cap(s, "alpha", minute=1)
        # execute calls: (1) capture-set query, (2) existing-version lookup → None
        db = _Db([_Result(scalars=[c1]), _Result(scalar=None)])
        version = record_report_version(db, s, generated_by="ai-engine")
        self.assertEqual(len(db.added), 1)
        self.assertIsInstance(version, SessionReportVersion)
        self.assertTrue(version.capture_set_hash)
        self.assertEqual(version.artifacts["treatments"], [{"area": "lip"}])
        # Overlay (user state) is NOT captured in the artifact bundle.
        self.assertNotIn("rejected_safety_flags", version.artifacts)


class RestoreTests(unittest.TestCase):
    def test_restore_sets_artifacts_and_preserves_overlay(self):
        s = _session()
        # A rejection (user state) is live on the session and MUST survive a restore.
        s.extracted_metadata = {"treatments": [{"area": "stale"}], "rejected_safety_flags": ["allergy|x"]}
        version = SessionReportVersion()
        version.artifacts = {
            "summary": "restored summary",
            "generated_report": "restored report",
            "treatments": [{"area": "cheek"}],
            "safety_flags": [{"kind": "allergy", "text": "y"}],
        }
        restore_report_version(s, version)
        self.assertEqual(s.summary, "restored summary")
        self.assertEqual(s.generated_report, "restored report")
        self.assertEqual(s.extracted_metadata["treatments"], [{"area": "cheek"}])
        self.assertEqual(s.extracted_metadata["safety_flags"], [{"kind": "allergy", "text": "y"}])
        self.assertEqual(s.extracted_metadata["generated_output_stale"], False)
        # Ground-truth invariant: the user's rejection is untouched by the restore.
        self.assertEqual(s.extracted_metadata["rejected_safety_flags"], ["allergy|x"])


if __name__ == "__main__":
    unittest.main()
