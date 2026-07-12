import unittest
import uuid
from datetime import datetime, timezone

from app.models import Artifact, Capture, CaptureStatus, CaptureType, Patient, PatientStatus, Session
from app.services.capture_storage import internal_source_file_content
from app.services.captures import (
    _archive_orphaned_ai_patient,
    _patient_created_by_capture,
    _re_effect_capture,
    _soft_delete_capture,
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

    def scalars(self):
        # A scripted list row → those rows; None → empty; a scalar → a one-item sequence.
        if isinstance(self._row, list):
            return list(self._row)
        return [] if self._row is None else [self._row]


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
        # no dependent session, no live capture; then the archive-lifecycle hooks query (and find
        # none of) the patient's worklist entries, shares, and Q&A threads.
        db = _ScriptedDb(p, results=[None, None, [], [], []])
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


def _live_capture(*, artifact_id=None):
    c = Capture()
    c.id = uuid.uuid4()
    c.tenant_id = uuid.uuid4()
    c.session_id = uuid.uuid4()
    c.capture_type = CaptureType.audio
    c.status = CaptureStatus.processed
    c.source_artifact_id = artifact_id or uuid.uuid4()
    c.capture_metadata = {"original_filename": "visit.webm", "transcript": {"text": "…"}}
    return c


class SoftDeleteGuaranteeTests(unittest.TestCase):
    """E17 finding 3 — a removal is a reversible SOFT delete; it never destroys media."""

    def test_soft_delete_sets_status_only_and_preserves_the_artifact_link(self):
        capture = _live_capture()
        artifact_id = capture.source_artifact_id
        now = datetime(2026, 7, 12, tzinfo=timezone.utc)
        _soft_delete_capture(capture, _Principal(capture.tenant_id, uuid.uuid4()), now)
        self.assertEqual(capture.status, CaptureStatus.deleted)
        # The pre-delete status is remembered; the artifact reference is UNTOUCHED (media not destroyed).
        self.assertEqual(capture.capture_metadata["status_before_delete"], "processed")
        self.assertEqual(capture.capture_metadata["deleted_at"], now.isoformat())
        self.assertEqual(capture.source_artifact_id, artifact_id)

    def test_re_effect_round_trips_status_and_clears_delete_markers(self):
        capture = _live_capture()
        artifact_id = capture.source_artifact_id
        _soft_delete_capture(capture, _Principal(capture.tenant_id, uuid.uuid4()), datetime.now(timezone.utc))
        _re_effect_capture(capture, datetime.now(timezone.utc))
        # Redo restores the exact prior live status and clears the delete markers; artifact still intact.
        self.assertEqual(capture.status, CaptureStatus.processed)
        self.assertNotIn("deleted_at", capture.capture_metadata)
        self.assertNotIn("status_before_delete", capture.capture_metadata)
        self.assertEqual(capture.source_artifact_id, artifact_id)


class _MediaDb:
    """Scripted DB for internal_source_file_content: returns the (soft-deleted) capture, then its artifact."""

    def __init__(self, capture, artifact):
        self._rows = [capture, artifact]
        self._i = 0

    def execute(self, *_a, **_k):
        row = self._rows[self._i]
        self._i += 1
        return _Result(row)


class _FakeStore:
    bucket = "b"

    def get_object_bytes(self, _key):
        return b"AUDIO-BYTES"


class MediaStillFetchableInternallyTests(unittest.TestCase):
    """E17 finding 3 regression — a de-effected audio capture's media stays fetchable internally."""

    def test_internal_fetch_resolves_a_soft_deleted_capture(self):
        capture = _live_capture()
        _soft_delete_capture(capture, _Principal(capture.tenant_id, uuid.uuid4()), datetime.now(timezone.utc))
        self.assertEqual(capture.status, CaptureStatus.deleted)
        artifact = Artifact()
        artifact.id = capture.source_artifact_id
        artifact.tenant_id = capture.tenant_id
        artifact.object_key = "obj/key"
        artifact.mime_type = "audio/mp4"
        # The internal media path has NO status filter, so the AI engine / re-effect can still read it.
        result = internal_source_file_content(_MediaDb(capture, artifact), object_store=_FakeStore(), capture_id=str(capture.id))
        self.assertEqual(result["content"], b"AUDIO-BYTES")
        self.assertEqual(result["media_type"], "audio/mp4")


if __name__ == "__main__":
    unittest.main()
