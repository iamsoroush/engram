from celery import Celery

from ai_engine.config import settings
from ai_engine.observability import init_sentry

# Error tracking is initialized once, when the Celery app module is imported (before the worker
# starts). No-op when the DSN is empty (dev / unconfigured envs unaffected).
init_sentry()


celery_app = Celery(
    "notari_ai_engine",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["ai_engine.tasks"],
)

celery_app.conf.update(
    task_default_queue="ai_jobs",
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=600,
    task_soft_time_limit=540,
    # Redis broker priority: the worker drains the base (priority 0) queue before the suffixed
    # higher-number steps, so interactive jobs (default 0) are consumed before background sweep
    # refreshes (priority 6). Must match the backend's send-side options.
    broker_transport_options={"queue_order_strategy": "priority", "priority_steps": [0, 3, 6, 9]},
    beat_schedule={
        "recover-durable-ai-jobs": {
            "task": "ai_engine.recover_pending_ai_jobs",
            "schedule": settings.recovery_interval_seconds,
        },
    },
)
