"""The deterministic/LLM no-clobber guard: a current synthesis is kept only while content is unchanged.

`regenerate_session_report` skips rebuilding the deterministic floor (which would clobber the LLM
report) only when the synthesis is `current` AND the reportable content signature matches. These tests
lock the signature behaviour that makes that safe: stable for unchanged content, different on any
add/remove/edit.
"""
import unittest
import uuid
from types import SimpleNamespace

from app.models import CaptureType
from app.services.ai_jobs.reports import session_report_content_signature


def _capture(metadata, *, capture_type=CaptureType.audio, capture_id=None):
    return SimpleNamespace(id=capture_id or uuid.uuid4(), capture_type=capture_type, capture_metadata=metadata)


class ContentSignatureTests(unittest.TestCase):
    def test_same_content_same_signature(self):
        cid = uuid.uuid4()
        a = _capture({"transcript": {"text": "two cc gel left cheek"}}, capture_id=cid)
        b = _capture({"transcript": {"text": "two cc gel left cheek"}}, capture_id=cid)
        self.assertEqual(session_report_content_signature([a]), session_report_content_signature([b]))

    def test_order_independent(self):
        a = _capture({"transcript": {"text": "alpha"}})
        b = _capture({"caption": {"text": "beta"}}, capture_type=CaptureType.photo)
        self.assertEqual(session_report_content_signature([a, b]), session_report_content_signature([b, a]))

    def test_edited_text_changes_signature(self):
        cid = uuid.uuid4()
        before = _capture({"transcript": {"text": "two cc gel"}}, capture_id=cid)
        after = _capture({"transcript": {"text": "three cc gel"}}, capture_id=cid)
        self.assertNotEqual(session_report_content_signature([before]), session_report_content_signature([after]))

    def test_added_capture_changes_signature(self):
        a = _capture({"transcript": {"text": "alpha"}})
        b = _capture({"transcript": {"text": "beta"}})
        self.assertNotEqual(session_report_content_signature([a]), session_report_content_signature([a, b]))


if __name__ == "__main__":
    unittest.main()
