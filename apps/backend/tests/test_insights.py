"""Deterministic tests for clinic insights aggregation (owner/admin analytics).

Pure-logic style (no DB), mirroring ``test_smart_lists``: the analytically-tricky seams — range math,
bucketing, new-vs-returning, recency/age/sex classification, team share, treatment aggregation, the
carried-forward guard — are exercised over in-memory rows. The rules that must not break: deltas
compare an equal-length previous window; ``carriedForward`` treatments never inflate counts; a recall-
style "seen in window" patient counts as *new* only if their first-ever visit is inside the window.
"""

import unittest
import uuid
from datetime import date, datetime, timedelta, timezone

from app.services import insights
from app.services.insights import (
    CaptureRow,
    VisitRow,
    age_band,
    normalize_sex,
    normalize_unit,
    recency_bucket,
    resolve_window,
)

NOW = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)


def _visit(*, days_ago=0, patient=None, user=None, treatments=None):
    return VisitRow(
        session_id=uuid.uuid4(),
        patient_id=patient or uuid.uuid4(),
        created_by_user_id=user or uuid.uuid4(),
        when=NOW - timedelta(days=days_ago),
        treatments=treatments or [],
    )


def _treatment(area="forehead", product="botox", brand="Dysport", quantity=20, unit="u", **extra):
    base = {"area": area, "product": product, "brand": brand, "quantity": quantity, "unit": unit, "carriedForward": False}
    base.update(extra)
    return base


class ResolveWindowTests(unittest.TestCase):
    def test_previous_window_is_equal_length_and_precedes(self):
        w = resolve_window("last-3-months", now=NOW)
        self.assertEqual(w.end - w.start, timedelta(days=90))
        self.assertEqual(w.prev_end, w.start)
        self.assertEqual(w.start - w.prev_start, w.end - w.start)

    def test_this_month_starts_at_first_of_month(self):
        w = resolve_window("this-month", now=NOW)
        self.assertEqual((w.start.year, w.start.month, w.start.day), (2026, 7, 1))
        self.assertEqual(w.end, NOW)

    def test_long_windows_bucket_by_week_short_by_day(self):
        self.assertEqual(resolve_window("this-year", now=NOW).granularity, "week")
        self.assertEqual(resolve_window("this-week", now=NOW).granularity, "day")

    def test_unknown_range_falls_back_to_this_month(self):
        self.assertEqual(resolve_window("nonsense", now=NOW).range_key, "this-month")

    def test_custom_to_is_inclusive_day(self):
        w = resolve_window("custom", now=NOW, frm="2026-06-01", to="2026-06-30")
        self.assertEqual((w.start.month, w.start.day), (6, 1))
        self.assertEqual((w.end.month, w.end.day), (7, 1))  # exclusive end = day after 'to'


class ClassifierTests(unittest.TestCase):
    def test_normalize_sex_folds_common_and_persian_tokens(self):
        self.assertEqual(normalize_sex("Female"), "female")
        self.assertEqual(normalize_sex("مرد"), "male")
        self.assertEqual(normalize_sex("nonbinary"), "other")
        self.assertEqual(normalize_sex(None), "unknown")

    def test_age_band_boundaries(self):
        today = date(2026, 7, 2)
        self.assertEqual(age_band(date(2005, 7, 2), today), "18-25")  # exactly 21
        self.assertEqual(age_band(date(2009, 7, 3), today), "<18")    # 16 (birthday not yet)
        self.assertEqual(age_band(date(1960, 1, 1), today), "56+")
        self.assertIsNone(age_band(None, today))

    def test_recency_buckets(self):
        self.assertEqual(recency_bucket(NOW - timedelta(days=10), NOW), "active")
        self.assertEqual(recency_bucket(NOW - timedelta(days=120), NOW), "lapsing")
        self.assertEqual(recency_bucket(NOW - timedelta(days=400), NOW), "lapsed")
        self.assertIsNone(recency_bucket(None, NOW))

    def test_normalize_unit_families(self):
        self.assertEqual(normalize_unit("Units"), "u")
        self.assertEqual(normalize_unit("cc"), "ml")
        self.assertEqual(normalize_unit("ML"), "ml")
        self.assertIsNone(normalize_unit(None))


class NewVsReturningTests(unittest.TestCase):
    def test_new_only_when_first_ever_visit_is_in_window(self):
        window_start = NOW - timedelta(days=30)
        p_new, p_returning = uuid.uuid4(), uuid.uuid4()
        visits = [_visit(days_ago=2, patient=p_new), _visit(days_ago=3, patient=p_returning)]
        first_ever = {p_new: NOW - timedelta(days=2), p_returning: NOW - timedelta(days=200)}
        result = insights._new_vs_returning(visits, window_start, first_ever)
        self.assertEqual(result["new"], 1)
        self.assertEqual(result["returning"], 1)
        self.assertEqual(result["repeatRate"], 0.5)


class DeltaTests(unittest.TestCase):
    def test_delta_pct_and_zero_previous(self):
        self.assertEqual(insights._delta(120, 100)["pct"], 20.0)
        self.assertIsNone(insights._delta(5, 0)["pct"])  # no divide-by-zero; pct is None


class TeamTests(unittest.TestCase):
    def test_share_and_sort_by_patients(self):
        u1, u2 = uuid.uuid4(), uuid.uuid4()
        p1, p2, p3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        visits = [
            _visit(user=u1, patient=p1),
            _visit(user=u1, patient=p2),
            _visit(user=u2, patient=p3),
        ]
        captures = [CaptureRow(created_by_user_id=u1, patient_id=p1, when=NOW)]
        members = [{"userId": u1, "name": "Sara", "role": "doctor", "lastActiveAt": None},
                   {"userId": u2, "name": "Nima", "role": "doctor", "lastActiveAt": None}]
        team = insights._team_from_rows(members, visits, captures)
        self.assertEqual(team[0]["name"], "Sara")  # more patients → first
        self.assertEqual(team[0]["visits"], 2)
        self.assertEqual(team[0]["patients"], 2)
        self.assertEqual(team[0]["captures"], 1)
        self.assertAlmostEqual(team[0]["share"], round(2 / 3, 3))


class PatientsSnapshotTests(unittest.TestCase):
    def test_recency_age_and_sex_snapshot(self):
        pa, pb, pc = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        patients = [
            {"id": pa, "dob": date(1990, 1, 1), "sex": "female", "createdAt": NOW - timedelta(days=400)},
            {"id": pb, "dob": date(1980, 1, 1), "sex": "male", "createdAt": NOW - timedelta(days=10)},
            {"id": pc, "dob": None, "sex": None, "createdAt": NOW - timedelta(days=5)},  # never visited
        ]
        last_visit = {pa: NOW - timedelta(days=5), pb: NOW - timedelta(days=200)}
        snap = insights._patients_from_rows(patients, last_visit, NOW)
        self.assertEqual(snap["recency"], {"active": 1, "lapsing": 0, "lapsed": 1, "neverVisited": 1})
        self.assertEqual(snap["sexSplit"], {"female": 1, "male": 1, "other": 0, "unknown": 1})
        ages = {row["band"]: row["count"] for row in snap["ageHistogram"]}
        self.assertEqual(ages["36-45"], 1)  # 1990 → 36
        self.assertEqual(ages["46-55"], 1)  # 1980 → 46
        self.assertEqual(ages["unknown"], 1)


class TreatmentsTests(unittest.TestCase):
    def test_ranks_products_areas_and_sums_consumption(self):
        window = resolve_window("this-month", now=NOW)
        visits = [
            _visit(days_ago=1, treatments=[_treatment(product="botox", brand="Dysport", area="forehead", quantity=20, unit="u")]),
            _visit(days_ago=2, treatments=[_treatment(product="botox", brand="Dysport", area="glabella", quantity=10, unit="u")]),
            _visit(days_ago=3, treatments=[_treatment(product="filler", brand="Juvederm", area="lips", quantity=1.0, unit="ml")]),
        ]
        result = insights._treatments_from_visits(visits, window)
        self.assertEqual(result["topTreatments"][0], {"name": "botox", "count": 2})
        consumption = {row["unit"]: row for row in result["consumption"]}
        self.assertEqual(consumption["u"]["total"], 30.0)
        self.assertEqual(consumption["ml"]["total"], 1.0)
        self.assertEqual(result["byArea"][0]["count"], 1)

    def test_carried_forward_treatments_are_excluded(self):
        window = resolve_window("this-month", now=NOW)
        visits = [
            _visit(days_ago=1, treatments=[_treatment(product="botox", quantity=20, unit="u")]),
            _visit(days_ago=2, treatments=[_treatment(product="botox", quantity=20, unit="u", carriedForward=True)]),
        ]
        result = insights._treatments_from_visits(visits, window)
        self.assertEqual(result["topTreatments"][0], {"name": "botox", "count": 1})  # carried-forward not counted
        self.assertEqual({row["unit"]: row["count"] for row in result["consumption"]}["u"], 1)


class HeatmapTests(unittest.TestCase):
    def test_dense_grid_counts_by_dow_and_hour(self):
        # NOW is a Thursday (weekday 3), hour 12.
        grid = insights._busy_heatmap([_visit(days_ago=0), _visit(days_ago=0)])
        self.assertEqual(grid[3][12], 2)
        self.assertEqual(sum(sum(row) for row in grid), 2)


if __name__ == "__main__":
    unittest.main()
