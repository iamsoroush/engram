from celery import Celery

from app.config import settings


celery_app = Celery(
    "engram_backend",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_default_queue="ai_jobs",
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=600,
    task_soft_time_limit=540,
    # Send-side Redis priority routing (must match the ai-engine worker's consume-side options) so a
    # background sweep refresh (priority 6) lands behind interactive jobs (default 0) in the queue.
    broker_transport_options={"queue_order_strategy": "priority", "priority_steps": [0, 3, 6, 9]},
)
