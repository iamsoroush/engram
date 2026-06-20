"""Deterministic tests for Job 2 caption intelligence: the §7 needs-review marker and the
backend before/after photo-pairing step (both deterministic — no gateway)."""
import unittest

from app.services.ai_jobs.intents import CAPTION_LOW_CONFIDENCE_THRESHOLD, caption_review_marker
from app.services.photo_pairing import compute_photo_pairs


class CaptionReviewMarkerTests(unittest.TestCase):
    def test_low_confidence_raises_review(self):
        marker = caption_review_marker({"text": "Blurry cheek.", "confidence": 0.3, "uncertainties": []})
        self.assertIsNotNone(marker)
        self.assertTrue(marker["present"])
        self.assertEqual(marker["confidence"], 0.3)
        self.assertIn("review", marker["reason"].lower())

    def test_uncertainties_raise_review_with_reason(self):
        marker = caption_review_marker({"text": "A box.", "confidence": 0.9, "uncertainties": ["lot number unreadable"]})
        self.assertIsNotNone(marker)
        self.assertEqual(marker["reason"], "lot number unreadable")

    def test_confident_caption_no_review(self):
        self.assertIsNone(caption_review_marker({"text": "Clear left cheek.", "confidence": 0.95, "uncertainties": []}))

    def test_blank_caption_is_never_uncertain(self):
        # A Basic / no-gateway / manual-add caption is blank — not "AI unsure".
        self.assertIsNone(caption_review_marker({"text": "", "confidence": 0.0, "uncertainties": []}))
        self.assertIsNone(caption_review_marker({"text": "   "}))

    def test_threshold_boundary(self):
        # Exactly at the threshold is NOT low (strictly below triggers).
        self.assertIsNone(caption_review_marker({"text": "x", "confidence": CAPTION_LOW_CONFIDENCE_THRESHOLD, "uncertainties": []}))


def _photo(capture_id, **pairing):
    base = {"region": None, "laterality": None, "view": None, "phase": None, "isProductLabel": False}
    return {"captureId": capture_id, "pairing": {**base, **pairing}}


class PhotoPairingTests(unittest.TestCase):
    def test_before_after_same_site_pairs(self):
        photos = [
            _photo("a", region="cheek", laterality="left", view="front", phase="before"),
            _photo("b", region="cheek", laterality="left", view="front", phase="after"),
        ]
        pairs = compute_photo_pairs(photos)
        self.assertEqual(pairs["a"]["role"], "before")
        self.assertEqual(pairs["a"]["pairedCaptureId"], "b")
        self.assertEqual(pairs["b"]["role"], "after")
        self.assertEqual(pairs["b"]["pairedCaptureId"], "a")
        self.assertEqual(pairs["a"]["pairKey"], pairs["b"]["pairKey"])

    def test_different_site_not_paired(self):
        photos = [
            _photo("a", region="cheek", laterality="left", phase="before"),
            _photo("b", region="forehead", laterality="midline", phase="after"),
        ]
        pairs = compute_photo_pairs(photos)
        self.assertIsNone(pairs["a"]["pairedCaptureId"])
        self.assertIsNone(pairs["b"]["pairedCaptureId"])

    def test_two_unphased_same_site_pair_in_capture_order(self):
        photos = [
            _photo("first", region="lips", laterality="central", view="front"),
            _photo("second", region="lips", laterality="central", view="front"),
        ]
        pairs = compute_photo_pairs(photos)
        self.assertEqual(pairs["first"]["role"], "before")
        self.assertEqual(pairs["first"]["pairedCaptureId"], "second")
        self.assertEqual(pairs["second"]["role"], "after")

    def test_product_label_is_never_paired(self):
        photos = [
            _photo("label", isProductLabel=True, region="cheek"),
            _photo("a", region="cheek", laterality="left", phase="before"),
        ]
        pairs = compute_photo_pairs(photos)
        self.assertEqual(pairs["label"]["role"], "product-label")
        self.assertIsNone(pairs["label"]["pairedCaptureId"])

    def test_region_less_photo_is_single(self):
        pairs = compute_photo_pairs([_photo("a", phase="before")])
        self.assertEqual(pairs["a"]["role"], "single")
        self.assertIsNone(pairs["a"]["pairKey"])

    def test_three_with_one_extra_before_pairs_one(self):
        photos = [
            _photo("b1", region="cheek", laterality="left", phase="before"),
            _photo("b2", region="cheek", laterality="left", phase="before"),
            _photo("a1", region="cheek", laterality="left", phase="after"),
        ]
        pairs = compute_photo_pairs(photos)
        # First before pairs with the after; the extra before stays unpaired but keeps its role.
        self.assertEqual(pairs["b1"]["pairedCaptureId"], "a1")
        self.assertEqual(pairs["a1"]["pairedCaptureId"], "b1")
        self.assertEqual(pairs["b2"]["role"], "before")
        self.assertIsNone(pairs["b2"]["pairedCaptureId"])


if __name__ == "__main__":
    unittest.main()
