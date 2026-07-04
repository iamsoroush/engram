"""Characterization snapshot of the registered Celery task names (the deployment contract).

The task NAME is what queued messages carry, so a rename silently breaks any in-flight job routed
by the old name. This test DOCUMENTS the current registry (a change-detector) rather than forbidding
change: if a name is deliberately added/renamed, update ``EXPECTED_TASK_NAMES`` in the same commit —
the diff then makes the contract change visible in review. It exists so the ai_engine refactor
(splitting ``processing.py`` into ``core/`` + ``jobs/``) cannot move a task name by accident.
"""
import unittest

# Importing the tasks module registers every @celery_app.task on the shared app instance.
import ai_engine.tasks  # noqa: F401
from ai_engine.celery_app import celery_app

EXPECTED_TASK_NAMES = {
    "ai_engine.recover_pending_ai_jobs",
    "ai_engine.process_audio_capture",
    "ai_engine.process_text_capture",
    "ai_engine.process_image_capture",
    "ai_engine.process_session",
    "ai_engine.process_patient_memory",
    "ai_engine.process_qa_draft",
    "ai_engine.process_qa_revise",
}


class TaskNameSnapshotTests(unittest.TestCase):
    def test_registered_engram_task_names_match_snapshot(self):
        registered = {name for name in celery_app.tasks if name.startswith("ai_engine.")}
        self.assertEqual(
            registered,
            EXPECTED_TASK_NAMES,
            "Celery task names changed. If intentional, update EXPECTED_TASK_NAMES; a rename can "
            "orphan in-flight jobs queued under the old name.",
        )


if __name__ == "__main__":
    unittest.main()
