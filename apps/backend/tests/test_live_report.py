import unittest
import uuid
from types import SimpleNamespace

from app.services.ai_jobs import (
    has_append_intent,
    mark_session_report_contributions,
    report_contribution_effect,
    session_has_uncontributed_capture,
)
from app.services.session_processing import capture_is_out_of_context


def _capture(metadata, cid=None):
    return SimpleNamespace(capture_metadata=metadata, id=cid)


class _CapturesDb:
    """Minimal stand-in whose execute().scalars() yields a fixed capture list."""

    def __init__(self, captures):
        self._captures = captures

    def execute(self, _statement):
        return SimpleNamespace(scalars=lambda: list(self._captures))


class CaptureOutOfContextTests(unittest.TestCase):
    def test_present_marker_is_out_of_context(self):
        self.assertTrue(capture_is_out_of_context(_capture({"out_of_context": {"present": True}})))

    def test_absent_or_malformed_is_not_out_of_context(self):
        self.assertFalse(capture_is_out_of_context(_capture({})))
        self.assertFalse(capture_is_out_of_context(_capture(None)))
        self.assertFalse(capture_is_out_of_context(_capture({"out_of_context": {"present": False}})))
        self.assertFalse(capture_is_out_of_context(_capture({"out_of_context": "nonsense"})))

    def test_staff_override_clears_marker(self):
        # "Mark relevant" overrides the AI marker so the capture flows back into the report.
        self.assertFalse(
            capture_is_out_of_context(_capture({"out_of_context": {"present": True, "overridden_by_staff": True}}))
        )


class ReportContributionEffectTests(unittest.TestCase):
    def test_effect_shape(self):
        effect = report_contribution_effect("pending", had_append_intent=True)
        self.assertEqual(effect["type"], "report_contribution")
        self.assertEqual(effect["status"], "pending")
        self.assertTrue(effect["appendIntent"])
        self.assertIsNone(effect["generatedAt"])

    def test_added_effect_carries_generated_at(self):
        effect = report_contribution_effect("added", generated_at="2026-06-04T00:00:00Z")
        self.assertEqual(effect["status"], "added")
        self.assertEqual(effect["generatedAt"], "2026-06-04T00:00:00Z")
        self.assertFalse(effect["appendIntent"])


class HasAppendIntentTests(unittest.TestCase):
    def test_present_append_intent(self):
        self.assertTrue(has_append_intent({"intents": {"append": {"present": True, "confidence": 0.7}}}))

    def test_absent_or_not_present(self):
        self.assertFalse(has_append_intent({}))
        self.assertFalse(has_append_intent({"intents": None}))
        self.assertFalse(has_append_intent({"intents": {"append": {"present": False}}}))
        self.assertFalse(has_append_intent({"intents": {}}))


class MarkSessionReportContributionsTests(unittest.TestCase):
    def test_marks_in_context_captures_and_counts_set_aside(self):
        in_context_a = _capture({"transcript": {"text": "a"}})
        in_context_b = _capture({"caption": {"text": "b"}})
        out_of_context = _capture({"out_of_context": {"present": True}})
        db = _CapturesDb([in_context_a, in_context_b, out_of_context])
        session = SimpleNamespace(tenant_id=uuid.uuid4(), id=uuid.uuid4())

        summary = mark_session_report_contributions(db, session=session, generated_at="2026-06-04T00:00:00Z")

        self.assertEqual(summary, {"included": 2, "set_aside": 1})
        self.assertEqual(in_context_a.capture_metadata["report_contribution"]["status"], "added")
        self.assertEqual(in_context_b.capture_metadata["report_contribution"]["status"], "added")
        # The set-aside capture is not contributed.
        self.assertNotIn("report_contribution", out_of_context.capture_metadata)


class ReportSelfHealTests(unittest.TestCase):
    def test_marks_only_captures_in_the_report_source_set(self):
        in_report = _capture({"transcript": {"text": "a"}}, cid="A")
        arrived_mid_job = _capture({"transcript": {"text": "b"}}, cid="B")
        db = _CapturesDb([in_report, arrived_mid_job])
        session = SimpleNamespace(tenant_id=uuid.uuid4(), id=uuid.uuid4())

        summary = mark_session_report_contributions(db, session=session, generated_at="t", source_capture_ids=["A"])

        self.assertEqual(summary, {"included": 1, "set_aside": 0})
        self.assertEqual(in_report.capture_metadata["report_contribution"]["status"], "added")
        # The capture that arrived while the job ran stays pending → next pass folds it in.
        self.assertNotIn("report_contribution", arrived_mid_job.capture_metadata)

    def test_uncontributed_capture_detection(self):
        all_added = _CapturesDb([_capture({"report_contribution": {"status": "added"}})])
        self.assertFalse(session_has_uncontributed_capture(all_added, tenant_id=uuid.uuid4(), session_id=uuid.uuid4()))

        has_pending = _CapturesDb(
            [_capture({"report_contribution": {"status": "added"}}), _capture({"report_contribution": {"status": "pending"}})]
        )
        self.assertTrue(session_has_uncontributed_capture(has_pending, tenant_id=uuid.uuid4(), session_id=uuid.uuid4()))

    def test_out_of_context_capture_is_not_uncontributed(self):
        # A set-aside capture is intentionally not in the report and must not trigger re-dispatch.
        db = _CapturesDb([_capture({"out_of_context": {"present": True}})])
        self.assertFalse(session_has_uncontributed_capture(db, tenant_id=uuid.uuid4(), session_id=uuid.uuid4()))


if __name__ == "__main__":
    unittest.main()
