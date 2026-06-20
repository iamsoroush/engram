"""Deterministic clinical-safety tests for Pro treatment-extraction post-processing.

This field WRITES DOSES, so the correction/addition/carry-forward/supersede logic that sits over the
LLM's `treatments[]` is asserted here with canned synthesis outputs (no gateway). The rule that must
never break: ambiguity is surfaced for confirmation and NOTHING is silently overwritten.
"""
import unittest

from app.services.session_processing import (
    SESSION_SYNTHESIS_OUTPUT_VERSION,
    finalize_session_synthesis_output,
    process_synthesized_treatments,
    render_treatment_performed_blocks,
    validate_synthesis_capture_ids,
)

CAP_A = "cap-a"
CAP_B = "cap-b"
PRIOR = "prior-visit-1"


def _treatment(**overrides):
    """A canned TreatmentItem (the A↔B contract shape) the LLM would emit."""
    base = {
        "area": "left cheek",
        "product": "gel",
        "brand": None,
        "quantity": 3,
        "unit": "cc",
        "quantityText": "۳ سی‌سی",
        "lot": None,
        "confidence": 0.9,
        "sourceCaptureIds": [CAP_B],
        "evidence": None,
        "carriedForward": False,
        "supersedesCaptureId": None,
        "attributes": {},
    }
    base.update(overrides)
    return base


def _categories(review):
    return {item["category"] for item in review}


class CorrectionVsAdditionTests(unittest.TestCase):
    def test_same_area_product_unit_restated_supersedes(self):
        # «ژل ۲ سی‌سی» then «ژل ۳ سی‌سی» on the same area → ONE corrected treatment that supersedes the
        # earlier capture; the supersede link is kept (auditable/undoable), no confirmation needed.
        treatments, review = process_synthesized_treatments(
            [_treatment(supersedesCaptureId=CAP_A)],
            valid_capture_ids=[CAP_A, CAP_B],
        )
        self.assertEqual(len(treatments), 1)
        self.assertEqual(treatments[0]["supersedesCaptureId"], CAP_A)
        self.assertEqual(review, [])

    def test_additive_cue_keeps_two_treatments(self):
        # «هم گونه چپ هم گونه راست» → two distinct treatments, neither superseding the other.
        treatments, review = process_synthesized_treatments(
            [_treatment(area="left cheek", sourceCaptureIds=[CAP_A]), _treatment(area="right cheek", sourceCaptureIds=[CAP_B])],
            valid_capture_ids=[CAP_A, CAP_B],
        )
        self.assertEqual(len(treatments), 2)
        self.assertEqual(review, [])

    def test_ambiguous_uncertainty_flags_and_keeps_both(self):
        # The LLM couldn't tell correction from addition → it emitted BOTH + an uncertainty sentence.
        # We surface the confirmation and keep both (NO silent overwrite).
        treatments, review = process_synthesized_treatments(
            [_treatment(quantity=2, quantityText="۲ سی‌سی"), _treatment(quantity=3, quantityText="۳ سی‌سی")],
            valid_capture_ids=[CAP_A, CAP_B],
            uncertainties=["Unclear whether 3cc corrects or adds to the 2cc gel on the left cheek."],
        )
        self.assertEqual(len(treatments), 2)
        self.assertIn("ambiguous", _categories(review))

    def test_unresolved_supersede_is_ambiguous_not_overwrite(self):
        # A correction cue whose superseded capture can't be resolved → clear the supersede link,
        # raise a confirmation item, and KEEP the treatment (never silently overwrite a dose).
        treatments, review = process_synthesized_treatments(
            [_treatment(supersedesCaptureId="ghost-capture")],
            valid_capture_ids=[CAP_A, CAP_B],
        )
        self.assertEqual(len(treatments), 1)
        self.assertIsNone(treatments[0]["supersedesCaptureId"])
        self.assertIn("ambiguous", _categories(review))


class CarryForwardTests(unittest.TestCase):
    def test_same_as_last_time_lowers_confidence_and_flags(self):
        treatment = _treatment(carriedForward=True, confidence=0.95, sourceCaptureIds=[PRIOR], quantityText="مثل دفعه قبل")
        treatments, review = process_synthesized_treatments(
            [treatment], valid_capture_ids=[CAP_A], prior_visit_capture_ids=[PRIOR]
        )
        self.assertEqual(len(treatments), 1)
        self.assertLessEqual(treatments[0]["confidence"], 0.6)
        # The prior-visit citation is preserved (it is an allowed carry-forward source).
        self.assertEqual(treatments[0]["sourceCaptureIds"], [PRIOR])
        self.assertIn("carried_forward", _categories(review))


class GuardrailTests(unittest.TestCase):
    def test_low_confidence_flags(self):
        _, review = process_synthesized_treatments([_treatment(confidence=0.3)], valid_capture_ids=[CAP_A, CAP_B])
        self.assertIn("low_confidence", _categories(review))

    def test_missing_but_expected_lot_flags(self):
        _, review = process_synthesized_treatments(
            [_treatment(lot=None, attributes={"lotExpected": True})], valid_capture_ids=[CAP_A, CAP_B]
        )
        self.assertIn("missing_lot", _categories(review))

    def test_unknown_source_capture_ids_are_dropped(self):
        treatments, _ = process_synthesized_treatments(
            [_treatment(sourceCaptureIds=[CAP_A, "ghost"])], valid_capture_ids=[CAP_A]
        )
        self.assertEqual(treatments[0]["sourceCaptureIds"], [CAP_A])


class RenderAndValidateTests(unittest.TestCase):
    def test_treatment_performed_line_is_verbatim_native_script(self):
        blocks = render_treatment_performed_blocks([_treatment(quantityText="۳ سی‌سی", brand="Juvederm", lot="LOT9")])
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["type"], "paragraph")
        text = blocks[0]["text"]
        self.assertIn("۳ سی‌سی", text)  # verbatim original script, not romanized/normalized
        self.assertIn("Juvederm", text)
        self.assertIn("LOT9", text)

    def test_validate_capture_ids_drops_unknown_image_and_reference(self):
        output = {
            "sections": [
                {
                    "id": "media",
                    "title": "Media",
                    "blocks": [
                        {"type": "image", "captureId": CAP_A, "caption": "kept"},
                        {"type": "image", "captureId": "ghost", "caption": "dropped"},
                        {"type": "paragraph", "text": "kept paragraph"},
                    ],
                }
            ],
            "sourceReferences": [
                {"type": "capture", "captureId": CAP_A},
                {"type": "capture", "captureId": "ghost"},
            ],
        }
        cleaned = validate_synthesis_capture_ids(output, [CAP_A])
        images = [block for block in cleaned["sections"][0]["blocks"] if block["type"] == "image"]
        self.assertEqual(images, [{"type": "image", "captureId": CAP_A, "caption": "kept"}])
        self.assertEqual(cleaned["sourceReferences"], [{"type": "capture", "captureId": CAP_A}])


class FinalizeEndToEndTests(unittest.TestCase):
    def test_finalize_rerenders_treatment_section_and_validates(self):
        # The model put STALE prose in treatment-performed and referenced a phantom photo — finalize
        # re-renders the section FROM treatments[] and drops the unknown image.
        output = {
            "schemaVersion": SESSION_SYNTHESIS_OUTPUT_VERSION,
            "summary": "Follow-up gel touch-up.",
            "language": "fa",
            "sections": [
                {"id": "treatment-performed", "title": "Treatment performed", "blocks": [{"type": "paragraph", "text": "STALE prose"}]},
                {"id": "media", "title": "Media", "blocks": [{"type": "image", "captureId": "ghost", "caption": "phantom"}]},
            ],
            "treatments": [_treatment(area="left cheek", product="gel", quantityText="۳ سی‌سی", sourceCaptureIds=[CAP_A])],
            "sourceReferences": [{"type": "capture", "captureId": CAP_A}],
            "uncertainties": [],
        }
        finalized, treatments, review = finalize_session_synthesis_output(output, valid_capture_ids=[CAP_A])
        treatment_section = next(section for section in finalized["sections"] if section["id"] == "treatment-performed")
        self.assertEqual(len(treatment_section["blocks"]), 1)
        self.assertIn("۳ سی‌سی", treatment_section["blocks"][0]["text"])
        self.assertNotIn("STALE", treatment_section["blocks"][0]["text"])
        media_section = next(section for section in finalized["sections"] if section["id"] == "media")
        self.assertEqual(media_section["blocks"], [])  # phantom image dropped
        self.assertEqual(len(treatments), 1)
        self.assertEqual(review, [])


if __name__ == "__main__":
    unittest.main()
