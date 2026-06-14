import unittest

from app.services.verticals import domain_descriptor, encounter_label, normalize_vertical


class VerticalsTests(unittest.TestCase):
    def test_encounter_label_per_vertical(self):
        self.assertEqual(encounter_label("aesthetics"), "Session")
        self.assertEqual(encounter_label("therapy"), "Session")
        self.assertEqual(encounter_label("dermatology"), "Visit")
        self.assertEqual(encounter_label("radiology"), "Study")
        self.assertEqual(encounter_label("pathology"), "Case")

    def test_unknown_or_missing_defaults_to_aesthetics_session(self):
        self.assertEqual(normalize_vertical(None), "aesthetics")
        self.assertEqual(normalize_vertical(""), "aesthetics")
        self.assertEqual(normalize_vertical("dental"), "aesthetics")
        self.assertEqual(encounter_label(None), "Session")
        self.assertEqual(encounter_label("dental"), "Session")

    def test_legacy_clinic_maps_to_aesthetics(self):
        self.assertEqual(normalize_vertical("clinic"), "aesthetics")
        self.assertEqual(encounter_label("clinic"), "Session")


class DomainDescriptorTests(unittest.TestCase):
    def test_aesthetics_and_therapy_have_distinct_framing(self):
        aes = domain_descriptor("aesthetics")
        self.assertEqual(aes["label"], "aesthetics clinic")
        self.assertIn("Botox", aes["vocabulary"])
        therapy = domain_descriptor("therapy")
        self.assertEqual(therapy["label"], "psychotherapy practice")
        self.assertNotIn("Botox", therapy["vocabulary"])

    def test_unknown_and_unmapped_verticals_degrade_to_neutral(self):
        # Unmapped (but valid) vertical → neutral, never an assumed clinic type.
        derm = domain_descriptor("dermatology")
        self.assertEqual(derm["label"], "clinic")
        self.assertEqual(derm["vocabulary"], [])
        # Unknown vertical normalizes to aesthetics (per normalize_vertical) — documented behavior.
        self.assertEqual(domain_descriptor("dental")["label"], "aesthetics clinic")


if __name__ == "__main__":
    unittest.main()
