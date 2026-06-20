import unittest
import uuid
from types import SimpleNamespace

from app.models import SessionStatus
from app.services.session_contracts import session_is_complete


def _session(metadata: dict) -> SimpleNamespace:
    # session_is_complete reads patient_id, generated_report, status, extracted_metadata.
    return SimpleNamespace(
        patient_id=uuid.uuid4(),
        generated_report="report body",
        status=SessionStatus.draft,
        extracted_metadata=metadata,
    )


class CarriedForwardGateTests(unittest.TestCase):
    """Q3: an unconfirmed carried-forward DOSE must not let a session read 'Complete'."""

    def test_unconfirmed_carried_forward_blocks_complete(self):
        s = _session({"treatment_review": [{"category": "carried_forward", "key": "cheeks|filler"}]})
        self.assertFalse(session_is_complete(s))

    def test_confirmed_carried_forward_allows_complete(self):
        s = _session(
            {
                "treatment_review": [{"category": "carried_forward", "key": "cheeks|filler"}],
                "confirmed_carried_forward": ["cheeks|filler"],
            }
        )
        self.assertTrue(session_is_complete(s))

    def test_other_review_items_do_not_block(self):
        # low-confidence / ambiguous / missing-lot stay non-blocking (warnings over blocking).
        s = _session({"treatment_review": [{"category": "low_confidence"}, {"category": "ambiguous"}]})
        self.assertTrue(session_is_complete(s))

    def test_no_review_completes(self):
        self.assertTrue(session_is_complete(_session({})))

    def test_partial_confirm_still_blocks(self):
        s = _session(
            {
                "treatment_review": [
                    {"category": "carried_forward", "key": "cheeks|filler"},
                    {"category": "carried_forward", "key": "lips|filler"},
                ],
                "confirmed_carried_forward": ["cheeks|filler"],
            }
        )
        self.assertFalse(session_is_complete(s))

    def test_stale_report_still_blocks(self):
        self.assertFalse(session_is_complete(_session({"generated_output_stale": True})))


if __name__ == "__main__":
    unittest.main()
