"""G6: the synthesis payload carries the prior reconcile decisions + candidate-set key for memoization."""
import unittest
from types import SimpleNamespace

from app.services.ai_jobs.worker import _prior_safety_reconciliation


class PriorSafetyReconciliationTests(unittest.TestCase):
    def test_returns_decisions_and_keys_when_both_present(self):
        session = SimpleNamespace(extracted_metadata={
            "safety_reconciliation": {"allergy|x": {"status": "keep", "ofKey": None}},
            "safety_reconciliation_keys": ["allergy|x", "consent|y"],
        })
        result = _prior_safety_reconciliation(session)
        self.assertEqual(result["candidateKeys"], ["allergy|x", "consent|y"])
        self.assertIn("allergy|x", result["decisions"])

    def test_none_when_decisions_absent_eg_after_reassignment(self):
        # A reassignment invalidates `safety_reconciliation`; without it the memo cannot reuse a stale
        # cross-patient decision set, so the reconcile re-runs for the corrected patient.
        session = SimpleNamespace(extracted_metadata={"safety_reconciliation_keys": ["allergy|x"]})
        self.assertIsNone(_prior_safety_reconciliation(session))

    def test_none_when_no_metadata(self):
        self.assertIsNone(_prior_safety_reconciliation(SimpleNamespace(extracted_metadata=None)))


if __name__ == "__main__":
    unittest.main()
