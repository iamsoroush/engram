import unittest
import uuid
from unittest.mock import patch

from app.services.patient_matching import MatchCandidate, find_patient_duplicates


def _candidate(matched_on: str, confidence: float, name: str = "Existing Patient", patient_id: uuid.UUID | None = None) -> MatchCandidate:
    return MatchCandidate(
        patient_id=patient_id or uuid.uuid4(),
        display_name=name,
        confidence=confidence,
        matched_on=[matched_on],
        reason="reason",
    )


class FindPatientDuplicatesTests(unittest.TestCase):
    """AES-205: deterministic near-match guard — surfaces likely existing matches, never merges."""

    def test_national_id_match_is_a_strong_duplicate(self):
        candidate = _candidate("national_id", 1.0)
        with (
            patch("app.services.patient_matching._exact_identifier_candidates", return_value=[candidate]),
            patch("app.services.patient_matching._exact_alias_candidates", return_value=[]),
            patch("app.services.patient_matching._fuzzy_alias_candidates", return_value=[]),
        ):
            result = find_patient_duplicates(object(), tenant_id=uuid.uuid4(), display_name="Whoever", national_id="0012345678")
        self.assertTrue(result["hasLikelyDuplicate"])
        self.assertEqual(result["candidates"][0]["matchedOn"], ["national_id"])

    def test_fuzzy_name_only_is_surfaced_but_not_flagged_strong(self):
        candidate = _candidate("fuzzy_alias", 0.8)
        with (
            patch("app.services.patient_matching._exact_identifier_candidates", return_value=[]),
            patch("app.services.patient_matching._exact_alias_candidates", return_value=[]),
            patch("app.services.patient_matching._fuzzy_alias_candidates", return_value=[candidate]),
        ):
            result = find_patient_duplicates(object(), tenant_id=uuid.uuid4(), display_name="سروش معاضد")
        self.assertFalse(result["hasLikelyDuplicate"])
        self.assertEqual(len(result["candidates"]), 1)

    def test_same_patient_from_two_signals_is_deduped_and_merged(self):
        patient_id = uuid.uuid4()
        nid = _candidate("national_id", 1.0, patient_id=patient_id)
        fuzzy = _candidate("fuzzy_alias", 0.7, patient_id=patient_id)
        with (
            patch("app.services.patient_matching._exact_identifier_candidates", return_value=[nid]),
            patch("app.services.patient_matching._exact_alias_candidates", return_value=[]),
            patch("app.services.patient_matching._fuzzy_alias_candidates", return_value=[fuzzy]),
        ):
            result = find_patient_duplicates(
                object(), tenant_id=uuid.uuid4(), display_name="سروش", national_id="0012345678"
            )
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(set(result["candidates"][0]["matchedOn"]), {"national_id", "fuzzy_alias"})
        self.assertTrue(result["hasLikelyDuplicate"])

    def test_no_signals_yields_no_candidates(self):
        with (
            patch("app.services.patient_matching._exact_identifier_candidates", return_value=[]),
            patch("app.services.patient_matching._exact_alias_candidates", return_value=[]),
            patch("app.services.patient_matching._fuzzy_alias_candidates", return_value=[]),
        ):
            result = find_patient_duplicates(object(), tenant_id=uuid.uuid4(), display_name="Nobody Here")
        self.assertFalse(result["hasLikelyDuplicate"])
        self.assertEqual(result["candidates"], [])


if __name__ == "__main__":
    unittest.main()
