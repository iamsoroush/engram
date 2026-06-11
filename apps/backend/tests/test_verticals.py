import unittest

from app.services.verticals import encounter_label, normalize_vertical


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


if __name__ == "__main__":
    unittest.main()
