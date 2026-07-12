import unittest
import uuid

from app.models import Session, SessionReportVersion
from app.services.report_versions import (
    derive_version_trigger,
    forward_version_count,
    in_context_capture_count,
    prune_forward_versions_on_branch,
    version_transition,
)


def _item(capture_id, *, content="h", out=False):
    return {"captureId": str(capture_id), "contentHash": content, "outOfContext": out}


def _version(items):
    v = SessionReportVersion()
    v.captured_capture_version_ids = list(items)
    return v


class _Cap:
    """A stand-in for a Capture — reachability only reads it back out of the removal list."""

    def __init__(self, capture_id):
        self.id = capture_id


class DeriveTriggerTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b, self.c = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        self.types = {self.a: "audio", self.b: "photo", self.c: "note"}

    def test_first_report_when_no_prior(self):
        self.assertEqual(derive_version_trigger(None, [_item(self.a)], self.types), {"kind": "first_report"})

    def test_single_add_uses_capture_type(self):
        prev = [_item(self.a)]
        self.assertEqual(derive_version_trigger(prev, [_item(self.a), _item(self.b)], self.types), {"kind": "photo_added"})
        self.assertEqual(derive_version_trigger([_item(self.b)], [_item(self.b), _item(self.a)], self.types), {"kind": "audio_added"})
        self.assertEqual(derive_version_trigger([_item(self.a)], [_item(self.a), _item(self.c)], self.types), {"kind": "note_added"})

    def test_multi_add_counts(self):
        got = derive_version_trigger([_item(self.a)], [_item(self.a), _item(self.b), _item(self.c)], self.types)
        self.assertEqual(got, {"kind": "captures_added", "count": 2})

    def test_removed(self):
        self.assertEqual(
            derive_version_trigger([_item(self.a), _item(self.b)], [_item(self.a)], self.types),
            {"kind": "capture_removed"},
        )
        self.assertEqual(
            derive_version_trigger([_item(self.a), _item(self.b), _item(self.c)], [_item(self.a)], self.types),
            {"kind": "captures_removed", "count": 2},
        )

    def test_content_edit_uses_type_specific_label(self):
        prev = [_item(self.a, content="h1"), _item(self.b, content="p1")]
        # audio content changed → transcript edited
        self.assertEqual(
            derive_version_trigger(prev, [_item(self.a, content="h2"), _item(self.b, content="p1")], self.types),
            {"kind": "transcript_edited"},
        )
        # photo content changed → caption edited
        self.assertEqual(
            derive_version_trigger(prev, [_item(self.a, content="h1"), _item(self.b, content="p2")], self.types),
            {"kind": "caption_edited"},
        )

    def test_out_of_context_toggle(self):
        prev = [_item(self.a, out=False)]
        self.assertEqual(derive_version_trigger(prev, [_item(self.a, out=True)], self.types), {"kind": "marked_out_of_context"})
        self.assertEqual(derive_version_trigger([_item(self.a, out=True)], [_item(self.a, out=False)], self.types), {"kind": "marked_relevant"})

    def test_mixed_add_and_remove_is_generic(self):
        self.assertEqual(
            derive_version_trigger([_item(self.a), _item(self.b)], [_item(self.a), _item(self.c)], self.types),
            {"kind": "report_updated"},
        )


class InContextCountTests(unittest.TestCase):
    def test_excludes_out_of_context(self):
        v = _version([_item("1"), _item("2", out=True), _item("3")])
        self.assertEqual(in_context_capture_count(v), 2)


class _Scalars:
    def __init__(self, rows):
        self._rows = list(rows)

    def __iter__(self):
        return iter(self._rows)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Scalars(self._rows)


class _QueuedDb:
    """Scripted DB: each execute() returns the next queued _Result (deleted-ids query, then versions)."""

    def __init__(self, results):
        self._results = list(results)
        self._i = 0

    def execute(self, *_a, **_k):
        result = self._results[self._i]
        self._i += 1
        return result


class ForwardBranchTests(unittest.TestCase):
    """E17 finding 2 — the forward (redo) branch is counted, and pruned when a new capture branches off."""

    def setUp(self):
        self.session = Session()
        self.session.id = uuid.uuid4()
        self.session.tenant_id = uuid.uuid4()
        self.deleted = str(uuid.uuid4())  # a currently soft-deleted capture
        self.live = str(uuid.uuid4())

    def _forward(self):
        return _version([_item(self.live), _item(self.deleted)])  # references a soft-deleted capture

    def _ancestor(self):
        return _version([_item(self.live)])  # references only live captures → NOT forward

    def test_forward_count_zero_without_soft_deleted_captures(self):
        # No soft-deleted captures → not behind head → 0, and the version query is never issued.
        db = _QueuedDb([_Result([])])
        self.assertEqual(forward_version_count(db, self.session), 0)

    def test_forward_count_counts_versions_referencing_a_deleted_capture(self):
        db = _QueuedDb([_Result([uuid.UUID(self.deleted)]), _Result([self._ancestor(), self._forward()])])
        self.assertEqual(forward_version_count(db, self.session), 1)  # only the forward version counts

    def test_prune_marks_only_the_forward_versions(self):
        ancestor, forward = self._ancestor(), self._forward()
        db = _QueuedDb([_Result([uuid.UUID(self.deleted)]), _Result([ancestor, forward])])
        pruned = prune_forward_versions_on_branch(db, self.session)
        self.assertEqual(pruned, 1)
        self.assertIsNone(ancestor.pruned_at)      # the current/ancestor line stays visible
        self.assertIsNotNone(forward.pruned_at)     # the abandoned forward line leaves the UI (row kept)

    def test_prune_is_a_noop_without_soft_deleted_captures(self):
        db = _QueuedDb([_Result([])])
        self.assertEqual(prune_forward_versions_on_branch(db, self.session), 0)


class TransitionTests(unittest.TestCase):
    """version_transition — the guard that decides restorability AND how to get there (undo + redo)."""

    def setUp(self):
        self.a, self.b, self.c = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        # All three captures exist as rows; a,b,c are live (none soft-deleted yet).
        self.all_by_id = {self.a: _Cap(self.a), self.b: _Cap(self.b), self.c: _Cap(self.c)}
        self.all_ooc = {self.a: False, self.b: False, self.c: False}
        self.live_ids = {self.a, self.b, self.c}

    def test_subset_version_soft_deletes_the_extra_captures(self):
        # A version over {a, b}: restoring (undo) soft-deletes exactly {c}, re-effects nothing.
        version = _version([_item(self.a), _item(self.b)])
        transition = version_transition(self.all_by_id, self.all_ooc, self.live_ids, version)
        self.assertIsNotNone(transition)
        self.assertEqual({c.id for c in transition.to_delete}, {self.c})
        self.assertEqual(transition.to_restore, ())
        self.assertFalse(transition.is_noop)

    def test_version_equal_to_current_is_a_noop(self):
        version = _version([_item(self.a), _item(self.b), _item(self.c)])
        transition = version_transition(self.all_by_id, self.all_ooc, self.live_ids, version)
        self.assertTrue(transition.is_noop)  # reachable, nothing to move → "already current"

    def test_forward_version_re_effects_a_soft_deleted_capture(self):
        # After a restore to {a,b}, c is soft-deleted (a row, not live). The FORWARD version {a,b,c} is
        # reachable by RE-EFFECTING c (redo) — never stranded (E17 finding 2).
        live_ids = {self.a, self.b}  # c currently soft-deleted
        version = _version([_item(self.a), _item(self.b), _item(self.c)])
        transition = version_transition(self.all_by_id, self.all_ooc, live_ids, version)
        self.assertIsNotNone(transition)
        self.assertEqual(transition.to_delete, ())
        self.assertEqual({c.id for c in transition.to_restore}, {self.c})
        self.assertFalse(transition.is_noop)

    def test_version_with_a_truly_gone_capture_is_unreachable(self):
        # A version knew a capture id that no longer exists as a row at all → cannot reproduce → None.
        gone = str(uuid.uuid4())
        version = _version([_item(self.a), _item(gone)])
        self.assertIsNone(version_transition(self.all_by_id, self.all_ooc, self.live_ids, version))

    def test_out_of_context_membership_mismatch_is_unreachable(self):
        # The version had `a` out-of-context, but `a` is currently in-context: a transition can't toggle
        # context back → not restorable (preview-only), never mis-restored.
        version = _version([_item(self.a, out=True), _item(self.b)])
        self.assertIsNone(version_transition(self.all_by_id, self.all_ooc, self.live_ids, version))


if __name__ == "__main__":
    unittest.main()
