"""Unit tests for the unified attention roll-up (Close-the-day / AES-1001).

Pure-unit: constructs ORM objects and exercises ``session_attention_items`` +
``aggregate_attention_items`` directly (no DB). The DB-driven ``build_attention_feed`` is covered by
the e2e-stack spec.
"""
import unittest
import uuid
from datetime import datetime, timezone
from typing import Any

from app.models import Session, SessionStatus
from app.services.attention import (
    TIER_CONFIRM,
    TIER_MESSAGES,
    TIER_SAFETY,
    TIER_SUGGESTED,
    _LocalToday,
    _day_group,
    aggregate_attention_items,
    session_attention_items,
)


def _session(
    *,
    status: SessionStatus = SessionStatus.needs_review,
    patient_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
    captured_at: datetime | None = None,
) -> Session:
    session = Session()
    session.id = uuid.uuid4()
    session.status = status
    session.patient_id = patient_id
    session.created_by_user_id = uuid.uuid4()
    session.captured_at = captured_at or datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)
    session.updated_at = session.captured_at
    session.created_at = session.captured_at
    session.extracted_metadata = metadata or {}
    return session


def _kinds(items: list[dict[str, Any]]) -> list[str]:
    return [item["kind"] for item in items]


class AssignmentDecisionTests(unittest.TestCase):
    def test_unassigned_without_candidate_is_assign_confirm(self) -> None:
        items = session_attention_items(
            _session(status=SessionStatus.unassigned), patient_name=None, has_patient_recheck=False
        )
        self.assertEqual(_kinds(items), ["assign-patient"])
        self.assertEqual(items[0]["tier"], TIER_CONFIRM)

    def test_possible_match_is_choose_patient(self) -> None:
        items = session_attention_items(
            _session(
                status=SessionStatus.unassigned,
                metadata={"patient_match": {"status": "possible_match", "risks": []}},
            ),
            patient_name=None,
            has_patient_recheck=False,
        )
        self.assertEqual(_kinds(items), ["choose-patient"])

    def test_national_id_conflict_is_resolve_conflict(self) -> None:
        items = session_attention_items(
            _session(
                status=SessionStatus.unassigned,
                metadata={"patient_match": {"status": "possible_match", "risks": ["national id mismatch"]}},
            ),
            patient_name=None,
            has_patient_recheck=False,
        )
        self.assertEqual(_kinds(items), ["resolve-conflict"])

    def test_verify_fires_even_when_assigned(self) -> None:
        items = session_attention_items(
            _session(
                patient_id=uuid.uuid4(),
                metadata={"ai_patient_action": {"needsVerification": True}},
            ),
            patient_name="Sara",
            has_patient_recheck=False,
        )
        self.assertEqual(_kinds(items), ["verify"])
        self.assertEqual(items[0]["patientName"], "Sara")


class DoseAndSafetyTests(unittest.TestCase):
    def test_unconfirmed_carried_forward_dose_is_confirm(self) -> None:
        items = session_attention_items(
            _session(
                patient_id=uuid.uuid4(),
                metadata={
                    "treatment_review": [
                        {"category": "carried_forward", "key": "cheek|botox", "reason": "confirm the dose"}
                    ]
                },
            ),
            patient_name="Sara",
            has_patient_recheck=False,
        )
        self.assertEqual(_kinds(items), ["dose"])
        self.assertEqual(items[0]["tier"], TIER_CONFIRM)
        self.assertEqual(items[0]["key"], "cheek|botox")

    def test_confirmed_carried_forward_dose_is_silent(self) -> None:
        items = session_attention_items(
            _session(
                patient_id=uuid.uuid4(),
                metadata={
                    "treatment_review": [{"category": "carried_forward", "key": "cheek|botox", "reason": "x"}],
                    "confirmed_carried_forward": ["cheek|botox"],
                },
            ),
            patient_name="Sara",
            has_patient_recheck=False,
        )
        self.assertEqual(items, [])

    def test_low_confidence_and_missing_lot_are_not_rolled_up(self) -> None:
        # S4 notes stay as fix-at-source footnotes; they never enter the cross-session sweep.
        items = session_attention_items(
            _session(
                patient_id=uuid.uuid4(),
                metadata={
                    "treatment_review": [
                        {"category": "low_confidence", "reason": "x"},
                        {"category": "missing_lot", "reason": "y"},
                    ]
                },
            ),
            patient_name="Sara",
            has_patient_recheck=False,
        )
        self.assertEqual(items, [])

    def test_safety_flags_are_shown_not_counted(self) -> None:
        items = session_attention_items(
            _session(
                patient_id=uuid.uuid4(),
                metadata={"safety_flags": [{"kind": "allergy", "text": "lidocaine allergy"}]},
            ),
            patient_name="Reza",
            has_patient_recheck=False,
        )
        self.assertEqual(_kinds(items), ["safety-flag"])
        self.assertEqual(items[0]["tier"], TIER_SAFETY)
        self.assertEqual(items[0]["reason"], "lidocaine allergy")
        # Safety is excluded from the "to-do" total.
        aggregate = aggregate_attention_items(items)
        self.assertEqual(aggregate["counts"]["safety"], 1)
        self.assertEqual(aggregate["counts"]["total"], 0)
        self.assertEqual(aggregate["highestTier"], "safety")


class Batch1CandidateTests(unittest.TestCase):
    def test_inert_assignment_is_a_confirm_conflict(self) -> None:
        items = session_attention_items(
            _session(
                patient_id=uuid.uuid4(),
                metadata={
                    "patient_match_candidate": {
                        "status": "suggested_reassignment",
                        "inertAssignment": True,
                        "reason": "review",
                    }
                },
            ),
            patient_name="Sara",
            has_patient_recheck=False,
        )
        self.assertEqual(_kinds(items), ["inert-assignment"])
        self.assertEqual(items[0]["tier"], TIER_CONFIRM)

    def test_plain_reassignment_is_suggested(self) -> None:
        items = session_attention_items(
            _session(
                patient_id=uuid.uuid4(),
                metadata={"patient_match_candidate": {"status": "suggested_reassignment", "reason": "r"}},
            ),
            patient_name="Sara",
            has_patient_recheck=False,
        )
        self.assertEqual(_kinds(items), ["suggested-reassignment"])
        self.assertEqual(items[0]["tier"], TIER_SUGGESTED)

    def test_name_correction_and_unassign_are_suggested(self) -> None:
        for status, kind in (
            ("suggested_name_correction", "suggested-name-correction"),
            ("suggested_unassign", "suggested-unassign"),
        ):
            items = session_attention_items(
                _session(patient_id=uuid.uuid4(), metadata={"patient_match_candidate": {"status": status}}),
                patient_name="Sara",
                has_patient_recheck=False,
            )
            self.assertEqual(_kinds(items), [kind])
            self.assertEqual(items[0]["tier"], TIER_SUGGESTED)

    def test_patient_recheck_is_suggested(self) -> None:
        items = session_attention_items(
            _session(patient_id=uuid.uuid4()), patient_name="Sara", has_patient_recheck=True
        )
        self.assertEqual(_kinds(items), ["patient-recheck"])
        self.assertEqual(items[0]["tier"], TIER_SUGGESTED)


class AggregateTests(unittest.TestCase):
    def _item(self, tier: str, sort_time: str) -> dict[str, Any]:
        return {"tier": tier, "sortTime": sort_time}

    def test_counts_and_highest_tier_and_sort(self) -> None:
        items = [
            self._item(TIER_SUGGESTED, "2026-06-01T00:00:00+00:00"),
            self._item(TIER_CONFIRM, "2026-06-03T00:00:00+00:00"),
            self._item(TIER_MESSAGES, "2026-06-02T00:00:00+00:00"),
            self._item(TIER_CONFIRM, "2026-06-04T00:00:00+00:00"),
        ]
        aggregate = aggregate_attention_items(items)
        self.assertEqual(aggregate["counts"]["confirm"], 2)
        self.assertEqual(aggregate["counts"]["suggested"], 1)
        self.assertEqual(aggregate["counts"]["messages"], 1)
        self.assertEqual(aggregate["counts"]["total"], 4)
        # No safety → highest is confirm.
        self.assertEqual(aggregate["highestTier"], "confirm")
        # Newest-open first.
        self.assertEqual(aggregate["items"][0]["sortTime"], "2026-06-04T00:00:00+00:00")

    def test_empty_feed_has_no_highest_tier(self) -> None:
        aggregate = aggregate_attention_items([])
        self.assertIsNone(aggregate["highestTier"])
        self.assertEqual(aggregate["counts"]["total"], 0)

    def test_urgent_qa_escalates_above_safety(self) -> None:
        # A red-flagged patient question (AES-1801) tops even a safety flag — the bell escalates.
        items = [
            {"tier": TIER_SAFETY, "sortTime": "2026-06-02T00:00:00+00:00"},
            {"tier": TIER_MESSAGES, "urgent": True, "sortTime": "2026-06-03T00:00:00+00:00"},
            {"tier": TIER_MESSAGES, "sortTime": "2026-06-01T00:00:00+00:00"},
        ]
        aggregate = aggregate_attention_items(items)
        self.assertEqual(aggregate["counts"]["urgent"], 1)
        self.assertEqual(aggregate["counts"]["messages"], 2)  # urgent is a subset of messages
        self.assertEqual(aggregate["highestTier"], "urgent")

    def test_non_urgent_messages_do_not_escalate(self) -> None:
        aggregate = aggregate_attention_items([{"tier": TIER_MESSAGES, "sortTime": "2026-06-01T00:00:00+00:00"}])
        self.assertEqual(aggregate["counts"]["urgent"], 0)
        self.assertEqual(aggregate["highestTier"], "messages")


class DayGroupTests(unittest.TestCase):
    def test_today_vs_earlier_respects_tz_offset(self) -> None:
        # now = 2026-06-08 01:00 UTC; a Tehran client (+210 min) is already on 2026-06-08 04:30.
        now = datetime(2026, 6, 8, 1, 0, tzinfo=timezone.utc)
        local = _LocalToday(now, 210)
        # A capture at 2026-06-08 00:30 UTC → local 04:00 → today.
        self.assertEqual(_day_group("2026-06-08T00:30:00+00:00", local_today=local), "today")
        # A capture two days earlier → earlier (carry-over group).
        self.assertEqual(_day_group("2026-06-06T09:00:00+00:00", local_today=local), "earlier")

    def test_missing_time_is_earlier(self) -> None:
        local = _LocalToday(datetime(2026, 6, 8, 1, 0, tzinfo=timezone.utc), 0)
        self.assertEqual(_day_group(None, local_today=local), "earlier")


if __name__ == "__main__":
    unittest.main()
