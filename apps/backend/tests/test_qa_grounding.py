"""G4: qa_draft grounding helpers — recent-visit aftercare + this-thread prior turns.

DB-free (fake db + lightweight stand-ins, repo convention). They pin that the draft is grounded in the
aftercare THIS patient was given and in the thread's own earlier exchange (not doctor-wide answers).
"""
import unittest
import uuid
from types import SimpleNamespace

from app.services.qa import THREAD_HISTORY_TURNS, _recent_visit_aftercare, _thread_prior_turns, ROLE_DOCTOR, ROLE_PATIENT, R_SENT, Q_PENDING, Q_ANSWERED


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return iter(self._rows)


class _Db:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _statement):
        return _Result(self._rows)


def _aftercare_report(text: str) -> dict:
    return {"sections": [
        {"id": "visit-summary", "blocks": [{"type": "paragraph", "text": "summary"}]},
        {"id": "aftercare", "blocks": [{"type": "paragraph", "text": text}]},
    ]}


class RecentVisitAftercareTests(unittest.TestCase):
    def test_extracts_aftercare_section_prose_from_latest_visit(self):
        db = _Db([_aftercare_report("تا ۲۴ ساعت از ورزش سنگین پرهیز کنید.")])
        result = _recent_visit_aftercare(db, tenant_id=uuid.uuid4(), patient_id=uuid.uuid4())
        self.assertIn("ورزش سنگین", result)

    def test_none_when_no_aftercare_section(self):
        db = _Db([{"sections": [{"id": "visit-summary", "blocks": [{"type": "paragraph", "text": "x"}]}]}])
        self.assertIsNone(_recent_visit_aftercare(db, tenant_id=uuid.uuid4(), patient_id=uuid.uuid4()))


def _msg(role, status, body, *, mid=None, in_reply_to=None):
    return SimpleNamespace(id=mid or uuid.uuid4(), role=role, status=status, body=body, in_reply_to_id=in_reply_to)


class ThreadPriorTurnsTests(unittest.TestCase):
    def test_pairs_answered_questions_excludes_current_and_bounds(self):
        thread = SimpleNamespace(id=uuid.uuid4(), tenant_id=uuid.uuid4())
        current_id = uuid.uuid4()
        messages = []
        # Six answered exchanges + the current pending question.
        for i in range(6):
            q = _msg(ROLE_PATIENT, Q_ANSWERED, f"q{i}")
            messages.append(q)
            messages.append(_msg(ROLE_DOCTOR, R_SENT, f"a{i}", in_reply_to=q.id))
        messages.append(_msg(ROLE_PATIENT, Q_PENDING, "current question", mid=current_id))
        db = _Db(messages)
        turns = _thread_prior_turns(db, thread=thread, exclude_message_id=current_id)
        self.assertEqual(len(turns), THREAD_HISTORY_TURNS)  # bounded
        self.assertEqual(turns[-1], {"question": "q5", "answer": "a5"})  # newest kept, oldest-first
        self.assertTrue(all(t["question"] != "current question" for t in turns))  # current excluded

    def test_unanswered_questions_are_not_included(self):
        thread = SimpleNamespace(id=uuid.uuid4(), tenant_id=uuid.uuid4())
        pending = _msg(ROLE_PATIENT, Q_PENDING, "unanswered")
        db = _Db([pending])
        self.assertEqual(_thread_prior_turns(db, thread=thread, exclude_message_id=uuid.uuid4()), [])


if __name__ == "__main__":
    unittest.main()
