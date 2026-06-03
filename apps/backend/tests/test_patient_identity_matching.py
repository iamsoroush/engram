import unittest
import uuid
from unittest.mock import patch

from app.services.patient_identity import (
    deterministic_identifier_specs,
    normalize_iranian_phone,
    normalize_national_id,
    normalize_text_key,
    normalized_aliases_for_value,
)
from app.services.patient_matching import MatchCandidate, match_patient_from_patient_information
from app.services.patients import patient_information_has_explicit_identity


class PatientIdentityNormalizationTests(unittest.TestCase):
    def test_persian_arabic_variants_digits_and_marks_are_normalized(self):
        self.assertEqual(normalize_text_key("  سـارا كاظمي  ۱۲۳ "), "سارا کاظمی 123")
        self.assertEqual(normalize_national_id("۰۰۱-٢٣٤-5678"), "0012345678")

    def test_iranian_phone_normalization_handles_common_forms(self):
        self.assertEqual(normalize_iranian_phone("۰۹۱۲ ۳۴۵ ۶۷۸۹"), "+989123456789")
        self.assertEqual(normalize_iranian_phone("0098-912-345-6789"), "+989123456789")
        self.assertEqual(normalize_iranian_phone("9123456789"), "+989123456789")

    def test_alias_specs_include_native_and_latin_without_rewriting_display_name(self):
        aliases = normalized_aliases_for_value("سارا")
        self.assertIn("سارا", aliases)
        self.assertIn("sara", aliases)

        specs = deterministic_identifier_specs(display_name="Sara N.", legal_first_name=None, legal_last_name=None)
        alias_values = {spec["normalized_value"] for spec in specs if spec["identifier_type"] == "normalized_alias"}
        self.assertIn("sara n", alias_values)
        self.assertIn("saran", alias_values)
        self.assertEqual({spec["identifier_value"] for spec in specs}, {"Sara N."})

    def test_explicit_identity_requires_spoken_or_identifier_evidence(self):
        self.assertFalse(patient_information_has_explicit_identity({"standardized_display_name": "Soraya Ghasemi"}))
        self.assertTrue(patient_information_has_explicit_identity({"raw_mentioned_name": "ثریا قاسمی"}))
        self.assertTrue(patient_information_has_explicit_identity({"national_id": "0012345678"}))


class PatientMatchingOrderTests(unittest.TestCase):
    def test_exact_national_id_wins_before_contact_or_alias_candidates(self):
        tenant_id = uuid.uuid4()
        national_candidate = MatchCandidate(
            patient_id=uuid.uuid4(),
            display_name="National ID Patient",
            confidence=1.0,
            matched_on=["national_id"],
            reason="national id",
        )
        phone_candidate = MatchCandidate(
            patient_id=uuid.uuid4(),
            display_name="Phone Patient",
            confidence=0.97,
            matched_on=["phone"],
            reason="phone",
        )

        with (
            patch(
                "app.services.patient_matching._exact_identifier_candidates",
                side_effect=[[national_candidate], [phone_candidate]],
            ) as exact,
            patch("app.services.patient_matching._exact_alias_candidates", return_value=[]) as exact_alias,
            patch("app.services.patient_matching._fuzzy_alias_candidates", return_value=[]) as fuzzy,
        ):
            result = match_patient_from_patient_information(
                object(),
                tenant_id=tenant_id,
                patient_information={
                    "standardized_display_name": "Other Name",
                    "national_id": "۰۰۱۲۳۴۵۶۷۸",
                    "phone": "09123456789",
                },
            )

        self.assertEqual(result["decision"], "matched")
        self.assertEqual(result["matchedOn"], ["national_id"])
        self.assertEqual(result["patientId"], str(national_candidate.patient_id))
        self.assertEqual(exact.call_count, 1)
        exact_alias.assert_not_called()
        fuzzy.assert_not_called()

    def test_fuzzy_candidates_are_capped_for_optional_llm_ranking(self):
        candidates = [
            MatchCandidate(
                patient_id=uuid.uuid4(),
                display_name=f"Candidate {index}",
                confidence=0.7,
                matched_on=["fuzzy_alias"],
                reason="fuzzy",
            )
            for index in range(8)
        ]
        with (
            patch("app.services.patient_matching._exact_identifier_candidates", return_value=[]),
            patch("app.services.patient_matching._exact_alias_candidates", return_value=[]),
            patch("app.services.patient_matching._fuzzy_alias_candidates", return_value=candidates),
        ):
            result = match_patient_from_patient_information(
                object(),
                tenant_id=uuid.uuid4(),
                patient_information={"standardized_display_name": "Sara Nazari"},
            )

        self.assertEqual(result["decision"], "possible_match")
        self.assertEqual(len(result["candidateSet"]), 5)
        self.assertTrue(result["llmRanking"]["eligible"])
        self.assertEqual(result["llmRanking"]["candidateCount"], 5)


class PatientMatchingConflictTests(unittest.TestCase):
    def _name_candidate(self):
        return MatchCandidate(
            patient_id=uuid.uuid4(),
            display_name="Name Patient",
            confidence=0.88,
            matched_on=["normalized_alias"],
            reason="alias",
        )

    def test_name_match_with_conflicting_national_id_goes_to_review(self):
        candidate = self._name_candidate()
        with (
            patch("app.services.patient_matching._exact_identifier_candidates", return_value=[]),
            patch("app.services.patient_matching._exact_alias_candidates", return_value=[candidate]),
            patch("app.services.patient_matching._fuzzy_alias_candidates", return_value=[]),
            patch("app.services.patient_matching._stored_national_ids", return_value={"9999999999"}),
        ):
            result = match_patient_from_patient_information(
                object(),
                tenant_id=uuid.uuid4(),
                patient_information={"standardized_display_name": "Soraya Ghasemi", "national_id": "0012345678"},
            )

        self.assertEqual(result["decision"], "possible_match")
        self.assertIsNone(result["patientId"])
        self.assertTrue(any("national ID" in risk for risk in result["risks"]))

    def test_name_match_without_national_id_conflict_assigns(self):
        candidate = self._name_candidate()
        with (
            patch("app.services.patient_matching._exact_identifier_candidates", return_value=[]),
            patch("app.services.patient_matching._exact_alias_candidates", return_value=[candidate]),
            patch("app.services.patient_matching._fuzzy_alias_candidates", return_value=[]),
            patch("app.services.patient_matching._stored_national_ids", return_value=set()),
        ):
            result = match_patient_from_patient_information(
                object(),
                tenant_id=uuid.uuid4(),
                patient_information={"standardized_display_name": "Soraya Ghasemi", "national_id": "0012345678"},
            )

        self.assertEqual(result["decision"], "matched")
        self.assertEqual(result["patientId"], str(candidate.patient_id))


if __name__ == "__main__":
    unittest.main()
