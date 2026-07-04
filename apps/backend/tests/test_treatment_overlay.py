"""Unit tests for the treatment-overlay mechanics (AES-1101): keys, fold, re-bind, auto-confirm."""
import unittest
from types import SimpleNamespace

from app.services.treatment_overlay import (
    compute_treatment_key,
    effective_treatments,
    norm_token,
    overlay_satisfied_carry_forward_keys,
    rebind_treatment_overlay,
    remove_overlay_edit,
    stamp_treatment_keys,
    upsert_overlay_edit,
)


def _session(treatments=None, overlay=None):
    return SimpleNamespace(extracted_metadata={"treatments": treatments or [], "treatment_overlay": overlay or []})


class NormAndKeyTests(unittest.TestCase):
    def test_norm_is_unicode_general(self):
        # NFKC + casefold + Unicode-wide digit fold + whitespace collapse.
        self.assertEqual(norm_token("  Left   Cheek "), "left cheek")
        self.assertEqual(norm_token("۲۰ واحد"), "20 واحد")  # Persian digits fold to Latin
        self.assertEqual(norm_token("GEL"), "gel")

    def test_key_anchors_on_area_code_when_present(self):
        key = compute_treatment_key({"areaCode": "Left-Cheek", "area": "گونه چپ", "product": "gel", "sourceCaptureIds": ["cap-a"]})
        self.assertEqual(key, "t|left-cheek|gel|cap-a")

    def test_key_falls_back_to_area_when_no_area_code(self):
        key = compute_treatment_key({"area": "Forehead", "product": "botox", "sourceCaptureIds": ["cap-b"]})
        self.assertEqual(key, "t|forehead|botox|cap-b")

    def test_stamp_disambiguates_collisions_with_ordinal(self):
        rows = [
            {"areaCode": "lips", "product": "filler", "sourceCaptureIds": ["cap-a"]},
            {"areaCode": "lips", "product": "filler", "sourceCaptureIds": ["cap-a"]},
        ]
        stamped = stamp_treatment_keys(rows)
        self.assertEqual(stamped[0]["treatmentKey"], "t|lips|filler|cap-a")
        self.assertEqual(stamped[1]["treatmentKey"], "t|lips|filler|cap-a#1")


class EffectiveTreatmentsTests(unittest.TestCase):
    def test_lot_edit_overrides_field(self):
        session = _session(
            treatments=[{"treatmentKey": "t|cheeks|gel|c1", "area": "cheeks", "product": "gel", "lot": "AI-000"}],
            overlay=[{"treatmentKey": "t|cheeks|gel|c1", "field": "lot", "value": "D-4471", "op": "edit"}],
        )
        folded = effective_treatments(session)
        self.assertEqual(folded[0]["lot"], "D-4471")  # the corrected lot reaches projections
        self.assertEqual(folded[0]["overlayEditedFields"], ["lot"])

    def test_quantity_edit_overrides_quantity_text_and_clears_numeric(self):
        session = _session(
            treatments=[{"treatmentKey": "t|cheeks|gel|c1", "quantity": 20, "unit": "units", "quantityText": "۲۰ واحد"}],
            overlay=[{"treatmentKey": "t|cheeks|gel|c1", "field": "quantity", "value": "24 units", "op": "edit"}],
        )
        folded = effective_treatments(session)
        self.assertEqual(folded[0]["quantityText"], "24 units")
        self.assertIsNone(folded[0]["quantity"])
        self.assertIsNone(folded[0]["unit"])

    def test_unedited_rows_pass_through_untouched(self):
        session = _session(treatments=[{"treatmentKey": "t|a|b|c", "lot": "X"}], overlay=[])
        self.assertEqual(effective_treatments(session), [{"treatmentKey": "t|a|b|c", "lot": "X"}])


class RebindTests(unittest.TestCase):
    def test_exact_key_binds_and_refreshes_ai_value(self):
        fresh = [{"treatmentKey": "t|cheeks|gel|c1", "area": "cheeks", "product": "gel", "lot": "AI-NEW", "sourceCaptureIds": ["c1"]}]
        overlay = [{"treatmentKey": "t|cheeks|gel|c1", "field": "lot", "value": "HUMAN", "aiValue": "AI-OLD", "op": "edit"}]
        rebound = rebind_treatment_overlay(fresh, overlay)
        self.assertEqual(len(rebound), 1)
        self.assertEqual(rebound[0]["value"], "HUMAN")
        self.assertEqual(rebound[0]["aiValue"], "AI-NEW")  # disagreement surfaces (HUMAN != AI-NEW)

    def test_shared_capture_and_area_rebinds_to_new_key(self):
        # The row re-keyed (e.g. product text drifted) but shares the source capture + area → re-bind.
        fresh = [{"treatmentKey": "t|cheeks|gel-x|c1", "areaCode": "cheeks", "product": "gel-x", "lot": "AI", "sourceCaptureIds": ["c1"]}]
        overlay = [{
            "treatmentKey": "t|cheeks|gel|c1", "field": "lot", "value": "HUMAN", "aiValue": "AI",
            "matchArea": "cheeks", "sourceCaptureIds": ["c1"], "op": "edit",
        }]
        rebound = rebind_treatment_overlay(fresh, overlay)
        self.assertEqual(rebound[0]["treatmentKey"], "t|cheeks|gel-x|c1")

    def test_prior_key_breaks_ties(self):
        fresh = [
            {"treatmentKey": "t|cheeks|a|c1", "areaCode": "cheeks", "product": "a", "sourceCaptureIds": ["c1"], "lot": "1"},
            {"treatmentKey": "t|cheeks|b|c1", "areaCode": "cheeks", "product": "b", "sourceCaptureIds": ["c1"], "priorKey": "t|cheeks|gel|c1", "lot": "2"},
        ]
        overlay = [{"treatmentKey": "t|cheeks|gel|c1", "field": "lot", "value": "H", "matchArea": "cheeks", "sourceCaptureIds": ["c1"], "op": "edit"}]
        rebound = rebind_treatment_overlay(fresh, overlay)
        self.assertEqual(rebound[0]["treatmentKey"], "t|cheeks|b|c1")  # the priorKey-claiming row wins

    def test_orphan_entry_drops(self):
        fresh = [{"treatmentKey": "t|other|x|c9", "areaCode": "other", "product": "x", "sourceCaptureIds": ["c9"]}]
        overlay = [{"treatmentKey": "t|cheeks|gel|c1", "field": "lot", "value": "H", "matchArea": "cheeks", "sourceCaptureIds": ["c1"], "op": "edit"}]
        self.assertEqual(rebind_treatment_overlay(fresh, overlay), [])


class AutoConfirmTests(unittest.TestCase):
    def test_dose_edit_satisfies_carried_forward_confirm(self):
        session = _session(
            treatments=[{"treatmentKey": "t|cheeks|gel|c1", "area": "cheeks", "product": "gel", "carriedForward": True}],
            overlay=[{"treatmentKey": "t|cheeks|gel|c1", "field": "quantity", "value": "2 cc", "op": "edit"}],
        )
        self.assertEqual(overlay_satisfied_carry_forward_keys(session), {"cheeks|gel"})

    def test_non_dose_edit_does_not_satisfy(self):
        session = _session(
            treatments=[{"treatmentKey": "t|cheeks|gel|c1", "area": "cheeks", "product": "gel", "carriedForward": True}],
            overlay=[{"treatmentKey": "t|cheeks|gel|c1", "field": "lot", "value": "X", "op": "edit"}],
        )
        self.assertEqual(overlay_satisfied_carry_forward_keys(session), set())


class UpsertRemoveTests(unittest.TestCase):
    def test_upsert_snapshots_ai_value_and_last_write_wins(self):
        treatment = {"treatmentKey": "t|cheeks|gel|c1", "quantity": 20, "unit": "units", "sourceCaptureIds": ["c1"], "areaCode": "cheeks"}
        overlay, ai_value = upsert_overlay_edit([], treatment=treatment, field="quantity", value="24 units", edited_by_user_id="u1")
        self.assertEqual(ai_value, "20 units")
        self.assertEqual(len(overlay), 1)
        # A second edit on the same (key, field) replaces the first.
        overlay2, _ = upsert_overlay_edit(overlay, treatment=treatment, field="quantity", value="26 units", edited_by_user_id="u1")
        self.assertEqual(len(overlay2), 1)
        self.assertEqual(overlay2[0]["value"], "26 units")

    def test_remove_drops_the_entry(self):
        overlay = [{"treatmentKey": "t|cheeks|gel|c1", "field": "lot", "value": "X", "op": "edit"}]
        self.assertEqual(remove_overlay_edit(overlay, treatment_key="t|cheeks|gel|c1", field="lot"), [])


if __name__ == "__main__":
    unittest.main()
