import unittest

from app.services.capabilities import (
    ALL_CAPABILITIES,
    CROSS_VISIT_SYNTHESIS,
    LIVE_REPORT_SYNTHESIS,
    TRANSCRIPTION,
    capabilities,
)


class CapabilitiesTests(unittest.TestCase):
    """The (vertical, tier) → capability matrix (P0.1). Pure; no DB."""

    def test_aesthetics_basic_is_the_deterministic_floor(self):
        # The Notes-killer: no AI capabilities at all.
        self.assertEqual(capabilities("aesthetics", "basic"), frozenset())

    def test_aesthetics_pro_is_the_full_set(self):
        self.assertEqual(capabilities("aesthetics", "pro"), ALL_CAPABILITIES)

    def test_legacy_clinic_behaves_like_aesthetics(self):
        self.assertEqual(capabilities("clinic", "pro"), ALL_CAPABILITIES)
        self.assertEqual(capabilities("clinic", "basic"), frozenset())

    def test_therapy_is_single_tier_full_set_regardless_of_tier(self):
        # Understanding floor: therapy always has the full set, including transcription.
        self.assertEqual(capabilities("therapy", "basic"), ALL_CAPABILITIES)
        self.assertEqual(capabilities("therapy", "pro"), ALL_CAPABILITIES)
        self.assertIn(TRANSCRIPTION, capabilities("therapy", "basic"))

    def test_dermatology_patterns_like_aesthetics(self):
        self.assertEqual(capabilities("dermatology", "basic"), frozenset())
        self.assertEqual(capabilities("dermatology", "pro"), ALL_CAPABILITIES)

    def test_unknown_vertical_and_tier_default_safely(self):
        self.assertEqual(capabilities(None, None), ALL_CAPABILITIES)  # unknown tier → pro
        self.assertEqual(capabilities("", "basic"), frozenset())
        self.assertEqual(capabilities("  AESTHETICS  ", "basic"), frozenset())  # trimmed + lowercased

    def test_pro_gated_caps_are_pro_only_in_aesthetics(self):
        for capability in (CROSS_VISIT_SYNTHESIS, LIVE_REPORT_SYNTHESIS):
            self.assertIn(capability, capabilities("aesthetics", "pro"))
            self.assertNotIn(capability, capabilities("aesthetics", "basic"))


if __name__ == "__main__":
    unittest.main()
