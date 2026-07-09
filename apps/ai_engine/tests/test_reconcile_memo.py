"""G6: cross-visit safety-reconcile memoization by candidate-flag-set key.

The reconcile is a second selection-only LLM call inside every synthesis. When synthesis re-runs on a
settle that doesn't touch safety flags, the candidate set is unchanged — so the prior decisions are
reused and the call is skipped. These pin the reuse-vs-recompute decision.
"""
import unittest

from ai_engine.jobs.session_synthesis import reconcile_memo_decisions

DECISIONS = {"allergy|x": {"status": "keep", "ofKey": None}, "consent|y": {"status": "duplicate", "ofKey": "allergy|x"}}


class ReconcileMemoTests(unittest.TestCase):
    def test_reuses_decisions_when_candidate_set_unchanged(self):
        prior = {"candidateKeys": ["consent|y", "allergy|x"], "decisions": DECISIONS}
        self.assertEqual(reconcile_memo_decisions(prior, ["allergy|x", "consent|y"]), DECISIONS)

    def test_recomputes_when_a_flag_is_added(self):
        prior = {"candidateKeys": ["allergy|x", "consent|y"], "decisions": DECISIONS}
        self.assertIsNone(reconcile_memo_decisions(prior, ["allergy|x", "consent|y", "contraindication|z"]))

    def test_recomputes_when_a_flag_is_removed(self):
        prior = {"candidateKeys": ["allergy|x", "consent|y"], "decisions": DECISIONS}
        self.assertIsNone(reconcile_memo_decisions(prior, ["allergy|x"]))

    def test_no_prior_memo_recomputes(self):
        self.assertIsNone(reconcile_memo_decisions(None, ["allergy|x", "consent|y"]))
        self.assertIsNone(reconcile_memo_decisions({}, ["allergy|x"]))
        self.assertIsNone(reconcile_memo_decisions({"candidateKeys": ["allergy|x"]}, ["allergy|x"]))  # no decisions


if __name__ == "__main__":
    unittest.main()
