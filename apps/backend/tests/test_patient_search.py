import unittest
import uuid

from app.models import Patient, PatientIdentifier
from app.services.patient_identity import normalized_aliases_for_value
from app.services.patient_search import (
    FUZZY_NAME_FLOOR,
    _match_patient,
    _QueryKeys,
)


def _identifier(identifier_type: str, normalized_value: str) -> PatientIdentifier:
    identifier = PatientIdentifier()
    identifier.identifier_type = identifier_type
    identifier.normalized_value = normalized_value
    return identifier


def _patient(display_name: str, *, phone: str | None = None, email: str | None = None) -> Patient:
    patient = Patient()
    patient.id = uuid.uuid4()
    patient.display_name = display_name
    patient.phone = phone
    patient.email = email
    return patient


def _name_identifiers(name: str) -> list[PatientIdentifier]:
    """Mirror real data: a stored name yields native + Latin normalized aliases (AES-204)."""
    return [_identifier("normalized_alias", alias) for alias in normalized_aliases_for_value(name)]


class MatchPatientLadderTests(unittest.TestCase):
    """The deterministic ranking ladder: exact identifier → exact name → prefix → fuzzy."""

    def test_exact_national_id_is_top(self):
        patient = _patient("Sara Nazari")
        identifiers = [_identifier("national_id", "0012345678")]
        match = _match_patient(_QueryKeys("۰۰۱۲۳۴۵۶۷۸"), patient=patient, identifiers=identifiers)
        self.assertEqual(match["matchedOn"], ["national_id"])
        self.assertEqual(match["score"], 1.0)

    def test_exact_phone(self):
        patient = _patient("Sara Nazari", phone="+989123456789")
        match = _match_patient(_QueryKeys("0912 345 6789"), patient=patient, identifiers=[])
        self.assertEqual(match["matchedOn"], ["phone"])
        self.assertGreater(match["score"], 0.9)

    def test_exact_name_folds_orthography(self):
        # Arabic yeh (علي) query must exact-match a patient stored with Persian yeh (علی).
        patient = _patient("علی")
        match = _match_patient(_QueryKeys("علي"), patient=patient, identifiers=_name_identifiers("علی"))
        self.assertEqual(match["matchedOn"], ["name"])
        self.assertEqual(match["score"], 0.95)

    def test_full_name_query_is_exact(self):
        patient = _patient("ثریا قاسمی")
        match = _match_patient(_QueryKeys("ثریا قاسمی"), patient=patient, identifiers=_name_identifiers("ثریا قاسمی"))
        self.assertEqual(match["matchedOn"], ["name"])

    def test_partial_last_name_is_fuzzy_hit(self):
        # A last-name-only query still surfaces the full-named patient (the core Persian case).
        patient = _patient("محمدرضا نظری")
        match = _match_patient(_QueryKeys("نظری"), patient=patient, identifiers=_name_identifiers("محمدرضا نظری"))
        self.assertEqual(match["matchedOn"], ["name_fuzzy"])
        self.assertGreaterEqual(match["score"], FUZZY_NAME_FLOOR)

    def test_unrelated_name_does_not_match(self):
        patient = _patient("بهروز جوادی")
        match = _match_patient(_QueryKeys("نظری"), patient=patient, identifiers=_name_identifiers("بهروز جوادی"))
        self.assertIsNone(match)

    def test_partial_national_id_digits(self):
        patient = _patient("Sara Nazari")
        identifiers = [_identifier("national_id", "0012345678")]
        match = _match_patient(_QueryKeys("2345"), patient=patient, identifiers=identifiers)
        self.assertEqual(match["matchedOn"], ["contact_partial"])

    def test_falls_back_to_patient_columns_when_no_identifier_rows(self):
        # A patient whose phone lives only on the column (no identifier row yet) still matches.
        patient = _patient("Sara Nazari", phone="09120000000")
        match = _match_patient(_QueryKeys("09120000000"), patient=patient, identifiers=[])
        self.assertEqual(match["matchedOn"], ["phone"])


class QueryKeysTests(unittest.TestCase):
    def test_query_keys_project_each_field(self):
        keys = _QueryKeys("  0912 345 6789 ")
        self.assertEqual(keys.phone, "+989123456789")
        keys_id = _QueryKeys("0012345678")
        self.assertEqual(keys_id.national_id, "0012345678")

    def test_name_candidates_include_native_and_latin(self):
        keys = _QueryKeys("قاسمی")
        self.assertIn("قاسمی", keys.name_candidates)
        self.assertIn("ghasmi", keys.name_candidates)


if __name__ == "__main__":
    unittest.main()
