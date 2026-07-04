"""Q&A reply-draft job (AES-402): draft a doctor's reply to a patient's between-visits question.

The doctor reviews and approves before anything is sent, so the draft is a warm, clinically-cautious
suggestion grounded in the doctor's prior answers + this patient's context, inventing no clinical
facts. Falls back to the backend-provided deterministic draft when gateway-less or the model returns
nothing usable, so the inbox always has a suggestion.
"""
from typing import Any

from ai_engine.contracts.qa import QA_DRAFT_OUTPUT_VERSION, parse_qa_draft_output  # noqa: F401
from ai_engine.core.backend_client import BackendClient
from ai_engine.core.gateway import gateway_client, resolve_model, transcription_is_configured
from ai_engine.core.util import utc_now
# The prompt lives in its own versioned module (§3.3); ``qa_draft_prompt`` is re-exported for the shim
# + tests, and the envelope stamps ``QA_DRAFT_PROMPT_VERSION``.
from ai_engine.prompts.qa_draft import PROMPT_VERSION as QA_DRAFT_PROMPT_VERSION
from ai_engine.prompts.qa_draft import build as qa_draft_prompt  # noqa: F401


def completed_qa_draft_output(payload: dict[str, Any]) -> dict[str, Any]:
    """Build the Q&A reply-draft output, via the gateway when configured.

    Falls back to the backend-provided deterministic draft when no gateway is configured or the
    model returns nothing usable, so the job always completes and the inbox always has a suggestion.
    """
    fallback = payload.get("deterministicFallback") if isinstance(payload.get("deterministicFallback"), dict) else {}

    def _fallback_output() -> dict[str, Any]:
        return {
            "schemaVersion": QA_DRAFT_OUTPUT_VERSION,
            "promptVersion": QA_DRAFT_PROMPT_VERSION,
            "draft": fallback.get("draft"),
            "source": fallback.get("source") or "mock-deterministic",
            "generated_by": "ai-engine",
            "generated_at": utc_now().isoformat(),
        }

    if not transcription_is_configured():
        return _fallback_output()

    ai_models = payload.get("aiModels") if isinstance(payload.get("aiModels"), dict) else None
    model = resolve_model("qa_draft", ai_models)
    client = gateway_client("qa_draft")
    # A gateway/network error propagates and is retried by the task wrapper (gateway_unavailable).
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": qa_draft_prompt(payload)}],
    )
    draft = parse_qa_draft_output(response.choices[0].message.content or "")
    if draft is None:
        return _fallback_output()
    return {
        "schemaVersion": QA_DRAFT_OUTPUT_VERSION,
        "promptVersion": QA_DRAFT_PROMPT_VERSION,
        "draft": draft,
        "source": f"ai:{model}",
        "model": model,
        "generated_by": "ai-engine",
        "generated_at": utc_now().isoformat(),
    }


def run_qa_draft_job(job_id: str, *, celery_task_id: str | None, retry_count: int) -> None:
    """Run a post-session patient Q&A reply-draft job through the backend API contract (AES-402)."""
    client = BackendClient()
    payload = client.start_job(job_id, celery_task_id=celery_task_id, retry_count=retry_count)
    job = payload["job"]
    if job.get("status") == "succeeded":
        return
    client.complete_job(job_id, output_key="qa_draft", output=completed_qa_draft_output(payload))
