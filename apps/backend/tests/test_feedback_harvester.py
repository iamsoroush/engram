import unittest
import uuid
from types import SimpleNamespace

from app.services.feedback import (
    record_capture_text_correction,
    record_text_correction,
    scrub_context,
    text_of,
)


class _FakeDb:
    """Captures ``db.add`` calls — the harvester only stages rows (like ``audit``), never flushes."""

    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


def _principal():
    return SimpleNamespace(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        user=SimpleNamespace(full_name="Dr Demo", email="dr@demo.clinic"),
    )


class ScrubContextTests(unittest.TestCase):
    def test_redacts_pii_keys_recursively(self):
        scrubbed = scrub_context(
            {
                "confidence": 0.91,
                "displayName": "سارا نادری",
                "match_candidate": {
                    "patientId": "p-1",
                    "confidence": 0.8,
                    "evidence": {"identifierValue": "0012345678"},
                    "reason": "matched on spoken name سارا",
                },
                "names": ["سارا", "Sara"],
            }
        )
        self.assertEqual(scrubbed["confidence"], 0.91)
        self.assertEqual(scrubbed["displayName"], "[redacted]")
        self.assertEqual(scrubbed["names"], "[redacted]")
        # Nested PII is redacted too, but non-PII structure is preserved for triage.
        self.assertEqual(scrubbed["match_candidate"]["patientId"], "p-1")
        self.assertEqual(scrubbed["match_candidate"]["confidence"], 0.8)
        self.assertEqual(scrubbed["match_candidate"]["evidence"], "[redacted]")
        self.assertEqual(scrubbed["match_candidate"]["reason"], "[redacted]")

    def test_non_pii_passthrough(self):
        self.assertEqual(scrub_context({"source": "capture-edit", "key": "forehead|botox"}),
                         {"source": "capture-edit", "key": "forehead|botox"})


class TextOfTests(unittest.TestCase):
    def test_dict_str_and_none(self):
        self.assertEqual(text_of({"text": "۲۰ واحد", "source": "ai"}), "۲۰ واحد")
        self.assertEqual(text_of("plain"), "plain")
        self.assertIsNone(text_of({"source": "ai"}))
        self.assertIsNone(text_of(None))
        self.assertIsNone(text_of(123))


class RecordTextCorrectionTests(unittest.TestCase):
    def test_no_event_when_unchanged(self):
        db = _FakeDb()
        record_text_correction(
            db, tenant_id=uuid.uuid4(), actor_user_id=uuid.uuid4(),
            ai_output_type="transcript", before="same", after=" same ",
        )
        self.assertEqual(db.added, [])

    def test_no_event_when_after_empty(self):
        db = _FakeDb()
        record_text_correction(
            db, tenant_id=uuid.uuid4(), actor_user_id=uuid.uuid4(),
            ai_output_type="caption", before="was", after="",
        )
        self.assertEqual(db.added, [])

    def test_stages_event_when_changed(self):
        db = _FakeDb()
        cap = uuid.uuid4()
        record_text_correction(
            db, tenant_id=uuid.uuid4(), actor_user_id=uuid.uuid4(),
            ai_output_type="transcript", before="معاضد", after="معاصد", capture_id=cap,
            context={"source": "capture-edit", "phone": "0912"},
        )
        self.assertEqual(len(db.added), 1)
        event = db.added[0]
        self.assertEqual(event.kind, "correction")
        self.assertEqual(event.ai_output_type, "transcript")
        self.assertEqual(event.before_value, "معاضد")
        self.assertEqual(event.after_value, "معاصد")
        self.assertEqual(event.capture_id, cap)
        # Context is scrubbed before persistence.
        self.assertEqual(event.context["source"], "capture-edit")
        self.assertEqual(event.context["phone"], "[redacted]")


class RecordCaptureTextCorrectionTests(unittest.TestCase):
    def test_caption_and_transcript_use_ai_original_as_before(self):
        db = _FakeDb()
        principal = _principal()
        capture = SimpleNamespace(id=uuid.uuid4(), session_id=uuid.uuid4(), patient_id=None)
        previous = {
            "ai_caption": {"text": "forehead, before", "source": "ai"},
            "caption": {"text": "forehead, before", "source": "ai"},
            "ai_transcript": {"text": "twenty units", "source": "ai"},
        }
        incoming = {
            "caption": {"text": "forehead — pre-treatment", "source": "staff_edit"},
            "transcript": {"text": "20 units botox", "source": "staff_edit"},
        }
        record_capture_text_correction(db, principal, capture, previous, incoming)
        kinds = {(e.ai_output_type, e.before_value, e.after_value) for e in db.added}
        self.assertIn(("caption", "forehead, before", "forehead — pre-treatment"), kinds)
        self.assertIn(("transcript", "twenty units", "20 units botox"), kinds)

    def test_ignores_non_staff_edit(self):
        db = _FakeDb()
        principal = _principal()
        capture = SimpleNamespace(id=uuid.uuid4(), session_id=uuid.uuid4(), patient_id=None)
        # An AI-sourced caption update is not a correction.
        record_capture_text_correction(
            db, principal, capture,
            {"caption": {"text": "old", "source": "ai"}},
            {"caption": {"text": "new", "source": "ai"}},
        )
        self.assertEqual(db.added, [])


if __name__ == "__main__":
    unittest.main()
