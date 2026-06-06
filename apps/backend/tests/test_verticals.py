import unittest

from app.services.verticals import encounter_label, normalize_vertical


class VerticalsTests(unittest.TestCase):
    def test_encounter_label_per_vertical(self):
        self.assertEqual(encounter_label("clinic"), "Session")
        self.assertEqual(encounter_label("radiology"), "Study")
        self.assertEqual(encounter_label("pathology"), "Case")

    def test_unknown_or_missing_defaults_to_clinic_session(self):
        self.assertEqual(normalize_vertical(None), "clinic")
        self.assertEqual(normalize_vertical("dental"), "clinic")
        self.assertEqual(encounter_label(None), "Session")
        self.assertEqual(encounter_label("dental"), "Session")


if __name__ == "__main__":
    unittest.main()
