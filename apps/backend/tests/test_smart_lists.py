"""Deterministic tests for smart lists + lot/product recall (AES-501 / AES-502).

Pure-logic style (no DB): the testable seams (``_ledger_from_pairs``, ``_recall_from_pairs``, the
list predicates, the lot-normalization rules, the unpaired-before photo predicate) take in-memory
(Session, Patient) fakes. The rule that must never break: a recall is **exact** — different spellings
of the same alphanumeric core are surfaced as *similar*, never folded into the affected list.
"""
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services import smart_lists
from app.services.smart_lists import (
    _group_by_patient,
    _due_to_return_rows,
    _ledger_from_pairs,
    _recall_from_pairs,
    _seen_this_week_rows,
    capture_is_unpaired_before,
    normalize_lot,
)

NOW = datetime.now(timezone.utc)


def _patient(name="Sara M.", phone="0912000", pid=None):
    return SimpleNamespace(id=pid or uuid.uuid4(), display_name=name, date_of_birth=None, sex=None, phone=phone)


def _session(*, days_ago=0, treatments=None, sid=None):
    when = NOW - timedelta(days=days_ago)
    return SimpleNamespace(
        id=sid or uuid.uuid4(),
        captured_at=when,
        updated_at=when,
        created_at=when,
        extracted_metadata={"treatments": treatments or []},
    )


def _treatment(area="forehead", product="botox", brand="Dysport", quantity=20, unit="u", lot=None, **extra):
    base = {
        "area": area,
        "product": product,
        "brand": brand,
        "quantity": quantity,
        "unit": unit,
        "quantityText": None,
        "lot": lot,
        "evidence": f"…lot {lot}…" if lot else None,
        "confidence": 0.9,
        "carriedForward": False,
    }
    base.update(extra)
    return base


class LotNormalizationTests(unittest.TestCase):
    def test_case_and_whitespace_fold_but_hyphens_kept(self):
        self.assertEqual(normalize_lot(" d-4471 "), "D-4471")
        self.assertEqual(normalize_lot("D-4471"), normalize_lot("d-4471"))
        # Internal whitespace collapses, but a hyphen is NOT a space — "D 4471" ≠ "D-4471".
        self.assertEqual(normalize_lot("D   4471"), "D 4471")
        self.assertNotEqual(normalize_lot("D 4471"), normalize_lot("D-4471"))
        self.assertNotEqual(normalize_lot("D4471"), normalize_lot("D-4471"))


class SeenThisWeekTests(unittest.TestCase):
    def test_only_visits_within_seven_days(self):
        recent = _patient("Recent")
        old = _patient("Old")
        pairs = [
            (_session(days_ago=2, treatments=[_treatment(lot="D-4471")]), recent),
            (_session(days_ago=30), old),
        ]
        rows = _seen_this_week_rows(_group_by_patient(pairs))
        self.assertEqual([r["displayName"] for r in rows], ["Recent"])
        # The content detail is the verbatim treatment phrase (brand + dose + area).
        self.assertEqual(rows[0]["detail"], "Dysport 20 u, forehead")


class DueToReturnTests(unittest.TestCase):
    def test_only_patients_past_threshold_longest_overdue_first(self):
        fresh = _patient("Fresh")
        lapsed = _patient("Lapsed")  # ~13 weeks
        long_gone = _patient("LongGone")  # ~30 weeks
        pairs = [
            (_session(days_ago=10), fresh),
            (_session(days_ago=91), lapsed),
            (_session(days_ago=210), long_gone),
        ]
        rows = _due_to_return_rows(_group_by_patient(pairs))
        self.assertEqual([r["displayName"] for r in rows], ["LongGone", "Lapsed"])  # oldest last-visit first

    def test_patient_with_a_recent_visit_is_not_due(self):
        # Latest visit is what counts — an old visit plus a recent one means NOT due.
        p = _patient("Returning")
        pairs = [(_session(days_ago=5), p), (_session(days_ago=200), p)]
        rows = _due_to_return_rows(_group_by_patient(pairs))
        self.assertEqual(rows, [])


class MissingAfterPhotoPredicateTests(unittest.TestCase):
    def test_before_without_pair_qualifies(self):
        self.assertTrue(capture_is_unpaired_before({"photo_pairing": {"role": "before", "pairedCaptureId": None}}))

    def test_paired_before_or_other_roles_do_not(self):
        self.assertFalse(capture_is_unpaired_before({"photo_pairing": {"role": "before", "pairedCaptureId": "cap-x"}}))
        self.assertFalse(capture_is_unpaired_before({"photo_pairing": {"role": "single", "pairedCaptureId": None}}))
        self.assertFalse(capture_is_unpaired_before({"photo_pairing": {"role": "after", "pairedCaptureId": None}}))
        self.assertFalse(capture_is_unpaired_before({}))
        self.assertFalse(capture_is_unpaired_before(None))


class LedgerTests(unittest.TestCase):
    def test_aggregates_lots_and_products_with_counts(self):
        a, b = _patient("A"), _patient("B")
        pairs = [
            (_session(treatments=[_treatment(lot="D-4471", brand="Dysport")]), a),
            (_session(treatments=[_treatment(lot="D-4471", brand="Dysport")]), b),
            (_session(treatments=[_treatment(lot="X-1", brand="Botox", product="botox")]), a),
        ]
        ledger = _ledger_from_pairs(pairs)
        by_lot = {row["lot"]: row for row in ledger["lots"]}
        self.assertEqual(by_lot["D-4471"]["patientCount"], 2)
        self.assertEqual(by_lot["D-4471"]["visitCount"], 2)
        self.assertEqual(by_lot["D-4471"]["brand"], "Dysport")
        self.assertEqual(by_lot["X-1"]["patientCount"], 1)
        # Most-used lot sorts first.
        self.assertEqual(ledger["lots"][0]["lot"], "D-4471")
        brands = {row["name"] for row in ledger["products"] if row["kind"] == "brand"}
        self.assertEqual(brands, {"Dysport", "Botox"})


class RecallTests(unittest.TestCase):
    def test_exact_lot_match_groups_by_patient_with_verbatim_treatment(self):
        sara, nima = _patient("Sara M."), _patient("Nima R.")
        pairs = [
            (_session(days_ago=5, treatments=[_treatment(lot="D-4471", area="forehead")]), sara),
            (_session(days_ago=40, treatments=[_treatment(lot="D-4471", area="glabella")]), nima),
            (_session(days_ago=1, treatments=[_treatment(lot="Z-9", area="cheek")]), sara),
        ]
        result = _recall_from_pairs(pairs, lot="d-4471", product=None)
        self.assertEqual(result["kind"], "lot")
        self.assertEqual(result["normalized"], "D-4471")
        self.assertEqual(result["patientCount"], 2)
        self.assertEqual(result["visitCount"], 2)
        # Most-recently-affected patient first; each row carries the verbatim, source-cited treatment.
        self.assertEqual(result["affected"][0]["displayName"], "Sara M.")
        treatment = result["affected"][0]["visits"][0]["treatments"][0]
        self.assertEqual(treatment["lot"], "D-4471")
        self.assertEqual(treatment["area"], "forehead")
        self.assertIn("D-4471", treatment["evidence"])

    def test_similar_spelling_is_not_folded_into_affected(self):
        # The safety rule: "D 4471" / "D4471" share a core with "D-4471" but are NOT the same lot.
        affected_p, similar_p = _patient("Affected"), _patient("Similar")
        pairs = [
            (_session(treatments=[_treatment(lot="D-4471")]), affected_p),
            (_session(treatments=[_treatment(lot="D 4471")]), similar_p),
            (_session(treatments=[_treatment(lot="D4471")]), similar_p),
        ]
        result = _recall_from_pairs(pairs, lot="D-4471", product=None)
        self.assertEqual(result["patientCount"], 1)
        self.assertEqual(result["affected"][0]["displayName"], "Affected")
        similar_lots = {row["lot"] for row in result["similar"]}
        self.assertEqual(similar_lots, {"D 4471", "D4471"})

    def test_product_recall_matches_brand_or_generic_case_insensitively(self):
        a, b = _patient("A"), _patient("B")
        pairs = [
            (_session(treatments=[_treatment(brand="Dysport", product="botox")]), a),
            (_session(treatments=[_treatment(brand="Juvederm", product="filler")]), b),
        ]
        by_brand = _recall_from_pairs(pairs, lot=None, product="dysport")
        self.assertEqual(by_brand["kind"], "product")
        self.assertEqual([r["displayName"] for r in by_brand["affected"]], ["A"])
        by_generic = _recall_from_pairs(pairs, lot=None, product="filler")
        self.assertEqual([r["displayName"] for r in by_generic["affected"]], ["B"])

    def test_empty_query_is_rejected(self):
        with self.assertRaises(Exception):
            _recall_from_pairs([], lot=None, product=None)


class CapabilityGateTests(unittest.TestCase):
    """Basic (no live_report_synthesis) is refused; Pro passes. Gates on the capability, not tier."""

    class _Db:
        def __init__(self, capable):
            self._capable = capable

        def execute(self, _statement):
            # tenant_capabilities() reads (vertical, tier); return aesthetics + the chosen tier.
            return SimpleNamespace(one_or_none=lambda: ("aesthetics", "pro" if self._capable else "basic"))

    def test_basic_tenant_is_forbidden(self):
        with self.assertRaises(Exception):
            smart_lists.require_smart_lists_capability(self._Db(False), uuid.uuid4())

    def test_pro_tenant_passes(self):
        # No raise == pass.
        smart_lists.require_smart_lists_capability(self._Db(True), uuid.uuid4())


if __name__ == "__main__":
    unittest.main()
