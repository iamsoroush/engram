"""G7: a `planned` treatment is stored with its status but never counts as performed.

Deterministic units over the apply layer (repo convention). Pins: status normalization, planned raises
no dose-confirmation review item, the treatment-performed prose excludes planned, and the performed
view filters planned out.
"""
import unittest

from app.services.session_processing import (
    TREATMENT_STATUS_PLANNED,
    process_synthesized_treatments,
    render_treatment_performed_blocks,
)
from app.services.treatment_overlay import performed_treatments_from_metadata


def _t(area, product, status=None, **extra):
    row = {"area": area, "product": product, "confidence": 0.9, "sourceCaptureIds": ["c1"], "carriedForward": False, "attributes": {}}
    if status is not None:
        row["status"] = status
    row.update(extra)
    return row


class ProcessSynthesizedTreatmentsStatusTests(unittest.TestCase):
    def test_absent_status_defaults_to_performed(self):
        processed, _ = process_synthesized_treatments([_t("لب", "ژل")], valid_capture_ids=["c1"])
        self.assertEqual(processed[0]["status"], "performed")

    def test_invalid_status_falls_back_to_performed(self):
        processed, _ = process_synthesized_treatments([_t("لب", "ژل", status="whatever")], valid_capture_ids=["c1"])
        self.assertEqual(processed[0]["status"], "performed")

    def test_planned_is_preserved(self):
        processed, _ = process_synthesized_treatments([_t("لب", "ژل", status="planned")], valid_capture_ids=["c1"])
        self.assertEqual(processed[0]["status"], "planned")

    def test_planned_low_confidence_raises_no_review_item(self):
        # A planned treatment is not administered — no dose to confirm, so no low-confidence review item.
        processed, review = process_synthesized_treatments(
            [_t("لب", "ژل", status="planned", confidence=0.1)], valid_capture_ids=["c1"]
        )
        self.assertEqual(processed[0]["status"], "planned")
        self.assertEqual(review, [])

    def test_performed_low_confidence_still_raises_review_item(self):
        _, review = process_synthesized_treatments([_t("لب", "ژل", confidence=0.1)], valid_capture_ids=["c1"])
        self.assertTrue(any(item["category"] == "low_confidence" for item in review))


class PerformedViewTests(unittest.TestCase):
    def test_render_treatment_performed_excludes_planned(self):
        blocks = render_treatment_performed_blocks([
            _t("پیشانی", "بوتاکس", status="performed", quantityText="۲۰ واحد"),
            _t("لب", "ژل", status=TREATMENT_STATUS_PLANNED, quantityText="۱ سی‌سی"),
        ])
        text = " ".join(b.get("text", "") for b in blocks)
        self.assertIn("بوتاکس", text)
        self.assertNotIn("ژل", text)  # the planned lip filler is not in the performed prose

    def test_performed_treatments_from_metadata_filters_planned(self):
        metadata = {"treatments": [
            _t("پیشانی", "بوتاکس", status="performed", treatmentKey="k1"),
            _t("لب", "ژل", status="planned", treatmentKey="k2"),
        ]}
        performed = performed_treatments_from_metadata(metadata)
        self.assertEqual([t["product"] for t in performed], ["بوتاکس"])


if __name__ == "__main__":
    unittest.main()
