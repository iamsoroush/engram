import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models import AiJobStatus
from app.services import ai_jobs


def make_job(**overrides):
    now = datetime(2026, 6, 2, tzinfo=timezone.utc)
    values = {
        "status": AiJobStatus.failed,
        "result_metadata": {},
        "attempt_count": 3,
        "next_retry_at": now,
        "last_dispatched_at": None,
        "last_attempted_at": None,
        "started_at": None,
        "created_at": now - timedelta(hours=1),
        "error_message": None,
        "last_error": None,
        "retry_reason": None,
        "completed_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class DurableAiJobRetryTests(unittest.TestCase):
    def test_retry_schedule_stays_retryable_after_exhausted_celery_attempts(self):
        now = datetime(2026, 6, 2, tzinfo=timezone.utc)
        job = make_job(attempt_count=5, next_retry_at=None)

        ai_jobs.schedule_retry(
            job,
            now=now,
            error_message="Audio transcription gateway timeout",
            retry_reason="gateway_unavailable",
        )

        self.assertEqual(job.status, AiJobStatus.failed)
        self.assertEqual(job.retry_reason, "gateway_unavailable")
        self.assertTrue(job.result_metadata["retryable"])
        self.assertGreater(job.next_retry_at, now)

    def test_recovery_waits_until_next_retry_at(self):
        now = datetime(2026, 6, 2, tzinfo=timezone.utc)
        job = make_job(next_retry_at=now + timedelta(minutes=5))

        self.assertFalse(ai_jobs.ai_job_due_for_recovery(job, now=now))

        job.next_retry_at = now
        self.assertTrue(ai_jobs.ai_job_due_for_recovery(job, now=now))

    def test_recently_dispatched_queued_job_is_not_recovered_tightly(self):
        now = datetime(2026, 6, 2, tzinfo=timezone.utc)
        job = make_job(
            status=AiJobStatus.queued,
            next_retry_at=None,
            last_dispatched_at=now - timedelta(seconds=10),
        )

        self.assertFalse(ai_jobs.ai_job_due_for_recovery(job, now=now))

    def test_stale_running_job_is_recovered(self):
        now = datetime(2026, 6, 2, tzinfo=timezone.utc)
        job = make_job(
            status=AiJobStatus.running,
            last_attempted_at=now - timedelta(seconds=ai_jobs.settings.ai_job_running_stale_seconds + 1),
            next_retry_at=None,
        )

        self.assertTrue(ai_jobs.ai_job_due_for_recovery(job, now=now))

    def test_non_retryable_job_is_skipped(self):
        now = datetime(2026, 6, 2, tzinfo=timezone.utc)
        job = make_job(result_metadata={"retryable": False}, next_retry_at=now)

        self.assertFalse(ai_jobs.ai_job_due_for_recovery(job, now=now))

    def test_deleted_capture_marker_is_terminal(self):
        now = datetime(2026, 6, 2, tzinfo=timezone.utc)
        job = make_job()

        ai_jobs.mark_job_non_retryable(
            job,
            now=now,
            reason="capture_deleted",
            error_message="AI job target capture is deleted",
        )

        self.assertEqual(job.status, AiJobStatus.failed)
        self.assertEqual(job.retry_reason, "capture_deleted")
        self.assertFalse(job.result_metadata["retryable"])
        self.assertIsNone(job.next_retry_at)


if __name__ == "__main__":
    unittest.main()
