import unittest
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.qa import (
    CARE_TEAM_BYLINE,
    Q_ANSWERED,
    Q_DISMISSED,
    Q_PENDING,
    R_SENT,
    ROLE_DOCTOR,
    ROLE_PATIENT,
    _capture_exchange_into_memory,
    _public_thread_projection,
    _qa_draft_fallback,
    _rank_treating_doctors,
)


def _msg(*, role, status, body, mid=None, in_reply_to_id=None, created_by_user_id=None, minute=0):
    return SimpleNamespace(
        id=mid or uuid.uuid4(),
        role=role,
        status=status,
        body=body,
        in_reply_to_id=in_reply_to_id,
        created_by_user_id=created_by_user_id,
        created_at=datetime(2026, 6, 13, 10, minute, tzinfo=timezone.utc),
    )


class RankTreatingDoctorsTests(unittest.TestCase):
    def test_most_visits_first(self):
        ranked = _rank_treating_doctors(
            [
                {"userId": "a", "name": "Dr A", "sessionCount": 1, "lastVisitAt": "2026-06-13T10:00:00+00:00"},
                {"userId": "b", "name": "Dr B", "sessionCount": 5, "lastVisitAt": "2026-01-01T10:00:00+00:00"},
            ]
        )
        self.assertEqual([d["userId"] for d in ranked], ["b", "a"])

    def test_recency_breaks_a_tie(self):
        ranked = _rank_treating_doctors(
            [
                {"userId": "old", "name": "Dr Z", "sessionCount": 2, "lastVisitAt": "2026-01-01T10:00:00+00:00"},
                {"userId": "new", "name": "Dr Y", "sessionCount": 2, "lastVisitAt": "2026-06-13T10:00:00+00:00"},
            ]
        )
        # Same visit count → most recent visit wins (treating-doctor default routing).
        self.assertEqual(ranked[0]["userId"], "new")

    def test_name_breaks_a_full_tie(self):
        ranked = _rank_treating_doctors(
            [
                {"userId": "z", "name": "Zara", "sessionCount": 1, "lastVisitAt": None},
                {"userId": "a", "name": "Adel", "sessionCount": 1, "lastVisitAt": None},
            ]
        )
        self.assertEqual([d["userId"] for d in ranked], ["a", "z"])

    def test_empty(self):
        self.assertEqual(_rank_treating_doctors([]), [])


class PublicThreadWithholdingTests(unittest.TestCase):
    """AES-403: the patient sees only their own questions + sent doctor replies — never drafts."""

    def _thread_messages(self):
        doctor_id = uuid.uuid4()
        q_answered = _msg(role=ROLE_PATIENT, status=Q_ANSWERED, body="Is swelling normal?", minute=0)
        reply = _msg(
            role=ROLE_DOCTOR,
            status=R_SENT,
            body="Yes, for a day or two.",
            in_reply_to_id=q_answered.id,
            created_by_user_id=doctor_id,
            minute=5,
        )
        q_awaiting = _msg(role=ROLE_PATIENT, status=Q_PENDING, body="Can I exercise?", minute=10)
        # Give the pending question a (withheld) AI draft to prove it never reaches the patient.
        q_awaiting.draft = "SECRET DRAFT the patient must never see"
        q_dismissed = _msg(role=ROLE_PATIENT, status=Q_DISMISSED, body="off-topic", minute=15)
        return [q_answered, reply, q_awaiting, q_dismissed], doctor_id

    def test_projection_shape_and_statuses(self):
        messages, doctor_id = self._thread_messages()
        payload = _public_thread_projection(
            clinic_name="Engram Demo Clinic",
            patient_name="Sara N.",
            messages=messages,
            doctor_names={doctor_id: "Dr. Demo"},
        )
        statuses = [(e["question"], e["status"], bool(e["reply"])) for e in payload["exchanges"]]
        self.assertEqual(
            statuses,
            [
                ("Is swelling normal?", "answered", True),
                ("Can I exercise?", "awaiting", False),
                ("off-topic", "closed", False),
            ],
        )
        # The sent reply is shown as doctor-verified with the doctor's byline.
        answered = payload["exchanges"][0]
        self.assertEqual(answered["reply"]["byline"], "Dr. Demo")
        self.assertTrue(answered["reply"]["verified"])

    def test_draft_never_leaks(self):
        messages, doctor_id = self._thread_messages()
        payload = _public_thread_projection(
            clinic_name="Clinic", patient_name="Sara", messages=messages, doctor_names={doctor_id: "Dr. Demo"}
        )
        import json

        serialized = json.dumps(payload)
        self.assertNotIn("SECRET DRAFT", serialized)
        self.assertNotIn("draft", serialized.lower())

    def test_byline_falls_back_to_care_team(self):
        q = _msg(role=ROLE_PATIENT, status=Q_ANSWERED, body="Q", minute=0)
        reply = _msg(role=ROLE_DOCTOR, status=R_SENT, body="A", in_reply_to_id=q.id, created_by_user_id=None, minute=1)
        payload = _public_thread_projection(clinic_name="C", patient_name="P", messages=[q, reply], doctor_names={})
        self.assertEqual(payload["exchanges"][0]["reply"]["byline"], CARE_TEAM_BYLINE)


class QaDraftFallbackTests(unittest.TestCase):
    def test_deterministic_draft_is_grounded_and_safe(self):
        draft = _qa_draft_fallback(
            question="Is the swelling normal?",
            doctor_name="Dr. Demo",
            prior_answers=[{"question": "swelling?", "answer": "usually normal"}],
            patient_context={"displayName": "Sara N.", "recentVisitSummaries": ["Forehead Botox 20u."]},
        )
        self.assertIn("Hi Sara", draft)          # personalized greeting
        self.assertIn("Forehead Botox 20u", draft)  # grounded in the recent visit
        self.assertIn("aftercare", draft.lower())   # points to aftercare
        self.assertIn("clinic", draft.lower())      # escalation path
        self.assertTrue(draft.strip().endswith("Dr. Demo"))  # signed by the doctor

    def test_handles_missing_name_and_history(self):
        draft = _qa_draft_fallback(question="Q?", doctor_name="the clinic", prior_answers=[], patient_context={})
        self.assertTrue(draft.startswith("Hi,"))
        self.assertIn("recent visit notes", draft)


class CaptureExchangeIntoMemoryTests(unittest.TestCase):
    def test_appends_bounded_entry(self):
        patient = SimpleNamespace(notes="Existing history.")
        _capture_exchange_into_memory(
            patient,
            question_text="Is the\nswelling   normal?",
            reply_text="Yes, for a day or two.",
            now=datetime(2026, 6, 13, tzinfo=timezone.utc),
        )
        self.assertIn("Existing history.", patient.notes)
        self.assertIn("[Q&A 2026-06-13]", patient.notes)
        self.assertIn("Patient asked: “Is the swelling normal?”", patient.notes)  # whitespace collapsed
        self.assertIn("Clinic replied: “Yes, for a day or two.”", patient.notes)

    def test_seeds_notes_when_empty(self):
        patient = SimpleNamespace(notes=None)
        _capture_exchange_into_memory(
            patient, question_text="Q", reply_text="A", now=datetime(2026, 6, 13, tzinfo=timezone.utc)
        )
        self.assertTrue(patient.notes.startswith("[Q&A 2026-06-13]"))


if __name__ == "__main__":
    unittest.main()
