import unittest
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.qa import (
    CARE_TEAM_BYLINE,
    DRAFT_NONE,
    DRAFT_READY,
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
    QA_REPLY_OUTPUT_TYPE,
    _record_qa_reply_feedback,
    _reset_pending_draft,
    _strip_greeting_name,
    _thread_language,
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
            language="en",
            messages=messages,
            doctor_names={doctor_id: "Dr. Demo"},
        )
        self.assertEqual(payload["language"], "en")  # Q-10: public page localizes to it
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
            clinic_name="Clinic", patient_name="Sara", language="en", messages=messages, doctor_names={doctor_id: "Dr. Demo"}
        )
        import json

        serialized = json.dumps(payload)
        self.assertNotIn("SECRET DRAFT", serialized)
        self.assertNotIn("draft", serialized.lower())

    def test_byline_falls_back_to_care_team(self):
        q = _msg(role=ROLE_PATIENT, status=Q_ANSWERED, body="Q", minute=0)
        reply = _msg(role=ROLE_DOCTOR, status=R_SENT, body="A", in_reply_to_id=q.id, created_by_user_id=None, minute=1)
        payload = _public_thread_projection(clinic_name="C", patient_name="P", language="fa", messages=[q, reply], doctor_names={})
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


class StripGreetingNameTests(unittest.TestCase):
    """Q-3: a stranger's name in a leading greeting must not survive into another patient's grounding."""

    def test_strips_english_greeting_name(self):
        self.assertEqual(_strip_greeting_name("Hi Maryam, swelling is normal."), "Hi, swelling is normal.")

    def test_strips_persian_greeting_name(self):
        self.assertEqual(_strip_greeting_name("سلام سارا، ورم طبیعی است."), "سلام، ورم طبیعی است.")

    def test_leaves_non_greeting_text_untouched(self):
        self.assertEqual(_strip_greeting_name("Swelling is normal for Maryam."), "Swelling is normal for Maryam.")

    def test_handles_none_and_empty(self):
        self.assertIsNone(_strip_greeting_name(None))
        self.assertEqual(_strip_greeting_name("   "), "   ")


class ThreadLanguageTests(unittest.TestCase):
    """Q-10: the public Q&A page localizes to the clinic language (configured, else content-inferred)."""

    def test_prefers_tenant_report_language(self):
        tenant = SimpleNamespace(report_language="fa")
        self.assertEqual(_thread_language(tenant, []), "fa")

    def test_infers_fa_from_persian_content(self):
        tenant = SimpleNamespace(report_language=None)
        messages = [_msg(role=ROLE_PATIENT, status=Q_PENDING, body="ورم طبیعی است؟")]
        self.assertEqual(_thread_language(tenant, messages), "fa")

    def test_defaults_to_en(self):
        self.assertEqual(_thread_language(None, [_msg(role=ROLE_PATIENT, status=Q_PENDING, body="Is this normal?")]), "en")


class _FakeDb:
    """Captures ``db.add`` — the qa harvester only stages a row in the caller's transaction."""

    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


class RecordQaReplyFeedbackTests(unittest.TestCase):
    """HALF-2: doctor actions on a draft become ai_feedback_events (qa_reply)."""

    def test_correction_recorded_when_edited(self):
        db = _FakeDb()
        _record_qa_reply_feedback(
            db, tenant_id=uuid.uuid4(), actor_user_id=uuid.uuid4(), patient_id=uuid.uuid4(),
            kind="correction", before="AI draft", after="doctor edit", context={"source": "send-edit"},
        )
        self.assertEqual(len(db.added), 1)
        self.assertEqual(db.added[0].ai_output_type, QA_REPLY_OUTPUT_TYPE)
        self.assertEqual(db.added[0].kind, "correction")

    def test_correction_skipped_when_unchanged(self):
        db = _FakeDb()
        _record_qa_reply_feedback(
            db, tenant_id=uuid.uuid4(), actor_user_id=uuid.uuid4(), patient_id=None,
            kind="correction", before="same text", after="same text", context=None,
        )
        self.assertEqual(db.added, [])  # no real edit → no signal

    def test_rejection_recorded(self):
        db = _FakeDb()
        _record_qa_reply_feedback(
            db, tenant_id=uuid.uuid4(), actor_user_id=uuid.uuid4(), patient_id=uuid.uuid4(),
            kind="rejection", before="drafted reply", after=None, context={"source": "dismiss"},
        )
        self.assertEqual(len(db.added), 1)
        self.assertEqual(db.added[0].kind, "rejection")


class ResetPendingDraftTests(unittest.TestCase):
    """Q-5: invalidation zeroes the draft AND its optimistic-lock job id so a stale job can't clobber."""

    def test_zeroes_all_draft_fields(self):
        question = SimpleNamespace(
            draft="signed by old doctor",
            draft_status=DRAFT_READY,
            draft_source="ai:model",
            draft_provenance={"kind": "template", "exemplarId": "x"},
            draft_job_id=uuid.uuid4(),
        )
        _reset_pending_draft(question)
        self.assertIsNone(question.draft)
        self.assertEqual(question.draft_status, DRAFT_NONE)
        self.assertIsNone(question.draft_source)
        self.assertIsNone(question.draft_provenance)
        self.assertIsNone(question.draft_job_id)


if __name__ == "__main__":
    unittest.main()
