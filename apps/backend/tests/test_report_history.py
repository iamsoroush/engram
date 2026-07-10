import unittest
import uuid

from app.models import SessionReportVersion
from app.services.report_versions import (
    derive_version_trigger,
    in_context_capture_count,
    removal_target_for_version,
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


class ReachabilityTests(unittest.TestCase):
    """removal_target_for_version — the safety-critical guard that decides restorability."""

    def setUp(self):
        self.a, self.b, self.c = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        # Current session has all three captures, all in-context.
        self.current_by_id = {self.a: _Cap(self.a), self.b: _Cap(self.b), self.c: _Cap(self.c)}
        self.current_ooc = {self.a: False, self.b: False, self.c: False}

    def test_subset_version_is_reachable_and_returns_the_extra_captures(self):
        # A version over {a, b}: restoring removes exactly {c}.
        version = _version([_item(self.a), _item(self.b)])
        removal = removal_target_for_version(self.current_by_id, self.current_ooc, version)
        self.assertIsNotNone(removal)
        self.assertEqual({c.id for c in removal}, {self.c})

    def test_version_equal_to_current_yields_empty_removal(self):
        version = _version([_item(self.a), _item(self.b), _item(self.c)])
        removal = removal_target_for_version(self.current_by_id, self.current_ooc, version)
        self.assertEqual(removal, [])  # reachable, nothing to remove → "already current"

    def test_version_with_a_now_deleted_capture_is_unreachable(self):
        # A version knew a capture id that no longer exists in the current set → cannot un-delete → None.
        gone = str(uuid.uuid4())
        version = _version([_item(self.a), _item(gone)])
        self.assertIsNone(removal_target_for_version(self.current_by_id, self.current_ooc, version))

    def test_out_of_context_membership_mismatch_is_unreachable(self):
        # The version had `a` out-of-context, but `a` is currently in-context: a pure removal can't toggle
        # context back → not restorable (preview-only), never mis-restored.
        version = _version([_item(self.a, out=True), _item(self.b)])
        self.assertIsNone(removal_target_for_version(self.current_by_id, self.current_ooc, version))


if __name__ == "__main__":
    unittest.main()
