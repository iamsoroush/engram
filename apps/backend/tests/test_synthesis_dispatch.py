"""Queue-collapse synthesis dispatch + cache-hit-before-dispatch (no timer, no debounce).

`maybe_dispatch_session_synthesis` is the single dispatch chokepoint. These tests lock the two decided
behaviours:
  * **Single-flight + one pending** — a trigger while any `session_organize` job is queued OR running
    is a no-op (`session_has_active_report_job`); the running job's completion re-invokes this to
    dispatch the one collapsed follow-up.
  * **Cache-hit before dispatch** — a recurring capture set restores a stored report_version
    deterministically instead of paying for a re-synthesis.

The collaborators (guards, session load, cache restore, create/dispatch) are patched so the tests
exercise the control flow rather than the DB.
"""
import unittest
import uuid
from types import SimpleNamespace
from unittest import mock

from app.services.ai_jobs import reports


class _FakeDb:
    """Returns a scripted session from execute().scalar_one_or_none(); records commits/refreshes."""

    def __init__(self, session):
        self._session = session
        self.commits = 0
        self.refreshed = []

    def execute(self, *_a, **_k):
        return SimpleNamespace(scalar_one_or_none=lambda: self._session)

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        self.refreshed.append(obj)


def _session():
    return SimpleNamespace(id=uuid.uuid4(), tenant_id=uuid.uuid4(), patient_id=None)


def _dispatch(db, **kw):
    return reports.maybe_dispatch_session_synthesis(
        db, tenant_id=uuid.uuid4(), session_id=uuid.uuid4(), **kw
    )


class MaybeDispatchTests(unittest.TestCase):
    def _patches(
        self, *, enabled=True, pending_jobs=False, active_job=False, uncontributed=True, cache_hit=False
    ):
        return [
            mock.patch.object(reports, "session_synthesis_enabled", return_value=enabled),
            mock.patch.object(reports, "session_has_pending_capture_jobs", return_value=pending_jobs),
            mock.patch.object(reports, "session_has_active_report_job", return_value=active_job),
            mock.patch.object(reports, "session_has_uncontributed_capture", return_value=uncontributed),
            mock.patch.object(reports, "restore_cached_session_synthesis", return_value=cache_hit),
            mock.patch.object(reports, "create_session_report_job", return_value=SimpleNamespace(id=uuid.uuid4())),
            mock.patch.object(reports, "dispatch_session_processing_job"),
        ]

    def _run(self, patches, db, **kw):
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5] as create, patches[6] as dispatch:
            _dispatch(db, **kw)
            return create, dispatch

    def test_dispatches_on_cache_miss_with_uncontributed_capture(self):
        db = _FakeDb(_session())
        create, dispatch = self._run(self._patches(cache_hit=False), db)
        create.assert_called_once()
        dispatch.assert_called_once()

    def test_cache_hit_restores_and_skips_dispatch(self):
        db = _FakeDb(_session())
        create, dispatch = self._run(self._patches(cache_hit=True), db)
        create.assert_not_called()
        dispatch.assert_not_called()
        self.assertEqual(db.commits, 1)  # the restore is committed

    def test_active_job_is_a_no_op(self):
        # Single-flight: a trigger while a job is queued OR running dispatches nothing (the queued job
        # reads the current set at start; a running job's completion drives the one follow-up).
        db = _FakeDb(_session())
        create, dispatch = self._run(self._patches(active_job=True), db)
        create.assert_not_called()
        dispatch.assert_not_called()

    def test_pending_capture_jobs_is_a_no_op(self):
        db = _FakeDb(_session())
        create, dispatch = self._run(self._patches(pending_jobs=True), db)
        create.assert_not_called()
        dispatch.assert_not_called()

    def test_all_contributed_without_force_is_a_no_op(self):
        db = _FakeDb(_session())
        create, dispatch = self._run(self._patches(uncontributed=False), db)
        create.assert_not_called()
        dispatch.assert_not_called()

    def test_force_dispatches_even_when_all_contributed(self):
        db = _FakeDb(_session())
        create, dispatch = self._run(self._patches(uncontributed=False, cache_hit=False), db, force=True)
        create.assert_called_once()
        dispatch.assert_called_once()

    def test_force_still_cache_hits_on_a_seen_set(self):
        # `force` keeps its meaning (re-synthesize past the all-contributed guard) but a set that
        # matches a stored version still restores deterministically — cheaper than an identical re-run.
        db = _FakeDb(_session())
        create, dispatch = self._run(self._patches(uncontributed=False, cache_hit=True), db, force=True)
        create.assert_not_called()
        dispatch.assert_not_called()

    def test_disabled_tenant_is_a_no_op(self):
        db = _FakeDb(_session())
        create, dispatch = self._run(self._patches(enabled=False), db)
        create.assert_not_called()
        dispatch.assert_not_called()


class RestoreCachedTests(unittest.TestCase):
    """`restore_cached_session_synthesis`: a hit restores + applies the overlay; a miss returns False."""

    def test_miss_returns_false(self):
        s = _session()
        with mock.patch("app.services.report_versions.find_report_version_for_current_set", return_value=None):
            self.assertFalse(reports.restore_cached_session_synthesis(SimpleNamespace(), session=s))

    def test_hit_restores_marks_and_returns_true(self):
        s = _session()
        s.extracted_metadata = {"source_capture_ids": ["c1"], "safety_flags": []}
        version = SimpleNamespace()
        db = SimpleNamespace(get=lambda *a, **k: None)
        with mock.patch("app.services.report_versions.find_report_version_for_current_set", return_value=version), \
             mock.patch("app.services.report_versions.restore_report_version") as restore, \
             mock.patch.object(reports, "mark_session_report_contributions") as mark:
            result = reports.restore_cached_session_synthesis(db, session=s)
        self.assertTrue(result)
        restore.assert_called_once_with(s, version)
        mark.assert_called_once()  # restored source captures flipped to `added`

    def test_hit_applies_overlay_to_patient(self):
        # Ground-truth invariant: on restore the user-state overlay is applied — the session's kept
        # flags are re-projected and the reconcile decisions re-applied, exactly like a fresh synthesis.
        patient = SimpleNamespace()
        db = SimpleNamespace(get=lambda *a, **k: patient)
        s = _session()
        s.patient_id = uuid.uuid4()
        s.extracted_metadata = {
            "safety_flags": [{"kind": "allergy", "text": "x"}],
            "safety_reconciliation": {"allergy|x": {"status": "keep"}},
        }
        with mock.patch("app.services.report_versions.find_report_version_for_current_set", return_value=SimpleNamespace()), \
             mock.patch("app.services.report_versions.restore_report_version"), \
             mock.patch.object(reports, "mark_session_report_contributions"), \
             mock.patch("app.services.patient_safety.sync_patient_safety_flags") as sync, \
             mock.patch("app.services.patient_safety.apply_safety_reconciliation") as reconcile:
            reports.restore_cached_session_synthesis(db, session=s)
        sync.assert_called_once_with(patient, s)
        reconcile.assert_called_once()


class SweepPendingTests(unittest.TestCase):
    """The catch-up safety net re-triggers only genuinely-stuck sessions and is a no-op otherwise."""

    def _db_with_sessions(self, sessions):
        return SimpleNamespace(execute=lambda *_a, **_k: SimpleNamespace(scalars=lambda: list(sessions)))

    def test_dispatches_for_stuck_session(self):
        s = _session()
        db = self._db_with_sessions([s])
        with mock.patch.object(reports, "session_has_pending_capture_jobs", return_value=False), \
             mock.patch.object(reports, "session_has_active_report_job", side_effect=[False, True]), \
             mock.patch.object(reports, "session_has_uncontributed_capture", return_value=True), \
             mock.patch.object(reports, "maybe_dispatch_session_synthesis") as dispatch:
            count = reports.sweep_pending_session_synthesis(db)
        dispatch.assert_called_once()
        self.assertEqual(count, 1)

    def test_skips_session_with_active_job(self):
        s = _session()
        db = self._db_with_sessions([s])
        with mock.patch.object(reports, "session_has_pending_capture_jobs", return_value=False), \
             mock.patch.object(reports, "session_has_active_report_job", return_value=True), \
             mock.patch.object(reports, "session_has_uncontributed_capture", return_value=True), \
             mock.patch.object(reports, "maybe_dispatch_session_synthesis") as dispatch:
            count = reports.sweep_pending_session_synthesis(db)
        dispatch.assert_not_called()
        self.assertEqual(count, 0)

    def test_skips_fully_contributed_session(self):
        s = _session()
        db = self._db_with_sessions([s])
        with mock.patch.object(reports, "session_has_pending_capture_jobs", return_value=False), \
             mock.patch.object(reports, "session_has_active_report_job", return_value=False), \
             mock.patch.object(reports, "session_has_uncontributed_capture", return_value=False), \
             mock.patch.object(reports, "maybe_dispatch_session_synthesis") as dispatch:
            count = reports.sweep_pending_session_synthesis(db)
        dispatch.assert_not_called()
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
