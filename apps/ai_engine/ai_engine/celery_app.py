from celery import Celery

from ai_engine.config import settings


celery_app = Celery(
    "aesmem_ai_engine",
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
    beat_schedule={
        "recover-durable-ai-jobs": {
            "task": "ai_engine.recover_pending_ai_jobs",
            "schedule": settings.recovery_interval_seconds,
        },
    },
)
