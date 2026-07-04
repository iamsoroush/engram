"""AI-job worker-callback request schemas (posted by the AI engine to /internal/ai/jobs/*)."""

from typing import Any

from pydantic import BaseModel


class AiJobStartRequest(BaseModel):
    celery_task_id: str | None = None
    retry_count: int = 0


class AiJobCompleteRequest(BaseModel):
    output_key: str
    output: dict[str, Any]
    # Real per-call gateway usage for this job (fair-use metering). One record per gateway call:
    # {task, model, promptTokens, completionTokens, audioSeconds?}. Absent for pre-metering workers.
    usage: list[dict[str, Any]] | None = None


class AiJobProgressRequest(BaseModel):
    output_key: str
    output: dict[str, Any]
    stage: str | None = None


class AiJobErrorRequest(BaseModel):
    error_message: str
    celery_task_id: str | None = None
    retry_count: int = 0
    retry_reason: str | None = None
