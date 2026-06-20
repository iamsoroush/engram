"""The Pro "organizing with AI" contract state.

While a Pro report-synthesis job is in flight (queued/running/retryable-failed), the deterministic
baseline already reads "complete" — so the session contract is nudged to a calm working state
(`state=processing`, `stage=organizing`) to keep the baseline visible AND signal AI is still working.
Basic / gateway-less tenants never dispatch such a job, so the indicator is never shown for them.
"""
import unittest
import uuid
from types import SimpleNamespace

from app.models import AiJobStatus, OrganizationSource, SessionStatus
from app.services.session_contracts import (
    SYNTHESIS_ORGANIZING_DETAIL,
    SYNTHESIS_ORGANIZING_LABEL,
    SYNTHESIS_ORGANIZING_STAGE,
    _has_inflight_synthesis_job,
    build_session_contracts,
)


class _JobsDb:
    """Minimal stand-in whose execute().scalars() yields a fixed AiJob list."""

    def __init__(self, jobs):
        self._jobs = jobs

    def execute(self, _statement):
        return SimpleNamespace(scalars=lambda: list(self._jobs))


def _job(status, *, retryable=True):
    return SimpleNamespace(status=status, result_metadata={"retryable": retryable})


def _complete_session():
    """A session whose deterministic baseline reads 'complete' (report processed, not stale)."""
    return SimpleNamespace(
        tenant_id=uuid.uuid4(),
        id=uuid.uuid4(),
        extracted_metadata={"capture_count": 2},  # no generated_output_stale → current
        generated_report="# Report\n\nVisit summary.",  # → report status "processed"
        generated_summary="A short summary.",
        summary="A short summary.",
        title="Visit",
        updated_at=None,
        status=SessionStatus.needs_review,  # not processing/failed
        organization_source=OrganizationSource.ai_engine,
        report_template_key="default",
    )


class HasInflightSynthesisJobTests(unittest.TestCase):
    def test_queued_or_running_is_inflight(self):
        session = SimpleNamespace(tenant_id=uuid.uuid4(), id=uuid.uuid4())
        self.assertTrue(_has_inflight_synthesis_job(_JobsDb([_job(AiJobStatus.queued)]), session))
        self.assertTrue(_has_inflight_synthesis_job(_JobsDb([_job(AiJobStatus.running)]), session))

    def test_retryable_failed_is_inflight_terminal_is_not(self):
        session = SimpleNamespace(tenant_id=uuid.uuid4(), id=uuid.uuid4())
        # A failed-but-retryable job (transient gateway error) is still going to run.
        self.assertTrue(_has_inflight_synthesis_job(_JobsDb([_job(AiJobStatus.failed, retryable=True)]), session))
        # A terminally failed job is done — the deterministic baseline is final.
        self.assertFalse(_has_inflight_synthesis_job(_JobsDb([_job(AiJobStatus.failed, retryable=False)]), session))

    def test_no_job_is_not_inflight(self):
        session = SimpleNamespace(tenant_id=uuid.uuid4(), id=uuid.uuid4())
        self.assertFalse(_has_inflight_synthesis_job(_JobsDb([]), session))


class OrganizingContractStateTests(unittest.TestCase):
    def test_complete_baseline_with_inflight_job_shows_organizing(self):
        contracts = build_session_contracts(_complete_session(), _JobsDb([_job(AiJobStatus.queued)]))
        status = contracts["processingStatus"]
        self.assertEqual(status["state"], "processing")
        self.assertEqual(status["stage"], SYNTHESIS_ORGANIZING_STAGE)
        self.assertEqual(status["label"], SYNTHESIS_ORGANIZING_LABEL)
        self.assertEqual(status["detail"], SYNTHESIS_ORGANIZING_DETAIL)
        # The baseline report itself stays intact/visible — only the processing status is nudged.
        self.assertEqual(contracts["report"]["status"], "processed")

    def test_complete_baseline_without_job_stays_complete(self):
        # Pro with no in-flight synthesis (settled), or Basic / gateway-less (never dispatches one).
        contracts = build_session_contracts(_complete_session(), _JobsDb([]))
        self.assertEqual(contracts["processingStatus"]["state"], "complete")

    def test_terminally_failed_job_stays_complete(self):
        contracts = build_session_contracts(_complete_session(), _JobsDb([_job(AiJobStatus.failed, retryable=False)]))
        self.assertEqual(contracts["processingStatus"]["state"], "complete")

    def test_settled_queued_baseline_with_inflight_job_shows_organizing(self):
        # A settled session whose derived state is "queued" (e.g. stale progressive_report metadata)
        # is still "baseline done, synthesis pending" — the organizing indicator must show there too.
        session = _complete_session()
        session.extracted_metadata = {"capture_count": 2, "progressive_report": {"status": "partial"}}
        baseline = build_session_contracts(session, _JobsDb([]))["processingStatus"]
        self.assertEqual(baseline["state"], "queued")  # not "processing"/"failed" → settled
        organizing = build_session_contracts(session, _JobsDb([_job(AiJobStatus.running)]))["processingStatus"]
        self.assertEqual(organizing["state"], "processing")
        self.assertEqual(organizing["stage"], SYNTHESIS_ORGANIZING_STAGE)

    def test_no_db_never_organizes(self):
        # Callers without a db session (degrade safely) never get a false organizing indicator.
        contracts = build_session_contracts(_complete_session())
        self.assertEqual(contracts["processingStatus"]["state"], "complete")

    def test_captures_still_processing_is_not_overridden(self):
        # While captures are still processing the generic working UI already applies — the organizing
        # override is skipped for the active `processing` state, so it must not fire here even with a job.
        session = _complete_session()
        session.status = SessionStatus.processing  # → derived state "processing" (captures in flight)
        contracts = build_session_contracts(session, _JobsDb([_job(AiJobStatus.running)]))
        self.assertEqual(contracts["processingStatus"]["state"], "processing")
        # ...and it is NOT tagged as the organizing stage (reserved for the settled-baseline case).
        self.assertNotEqual(contracts["processingStatus"].get("stage"), SYNTHESIS_ORGANIZING_STAGE)


if __name__ == "__main__":
    unittest.main()
