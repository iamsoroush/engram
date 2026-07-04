"""Q&A reply-draft job (AES-402): draft a doctor's reply to a patient's between-visits question.

The doctor reviews and approves before anything is sent, so the draft is a warm, clinically-cautious
suggestion grounded in the doctor's prior answers + this patient's context, inventing no clinical
facts. Falls back to the backend-provided deterministic draft when gateway-less or the model returns
nothing usable, so the inbox always has a suggestion.
"""
import json
from typing import Any

from ai_engine.core.backend_client import BackendClient
from ai_engine.core.gateway import gateway_client, resolve_model, transcription_is_configured
from ai_engine.core.util import utc_now


def qa_draft_prompt(payload: dict[str, Any]) -> str:
    """Build the prompt for a post-session patient Q&A reply draft (AES-402).

    The doctor reviews and approves the result before anything is sent, so the draft must be a warm,
    clinically-cautious *suggestion* grounded in the doctor's prior answers + this patient's context,
    inventing no clinical facts and escalating to the clinic when warranted.
    """
    qa = payload.get("qaDraft") if isinstance(payload.get("qaDraft"), dict) else {}
    return "\n\n".join(
        (
            "You are Engram, drafting a reply on behalf of an aesthetics clinic doctor to a patient's "
            "between-visits question. The doctor will review and edit before sending.",
            (
                "Write a warm, concise reply (2-4 sentences) in the patient's voice-appropriate register. "
                "Ground it in the doctor's PRIOR ANSWERS and THIS PATIENT'S CONTEXT below; match the "
                "doctor's tone. Do NOT invent clinical facts, doses, products, or diagnoses not present "
                "in the context. Reassure when appropriate, reference the aftercare already given, and "
                "tell the patient to contact the clinic if symptoms worsen or they are worried. Sign off "
                f"as {qa.get('doctorName') or 'the clinic'}. Return ONLY the plain-text reply."
            ),
            f"Patient question:\n{qa.get('patientQuestion', '')}",
            f"This patient's context:\n{json.dumps(qa.get('patientContext', {}), ensure_ascii=False, sort_keys=True)}",
            f"The doctor's prior answers:\n{json.dumps(qa.get('priorAnswers', []), ensure_ascii=False, sort_keys=True)}",
        )
    )


def parse_qa_draft_output(text: str) -> str | None:
    """Return a usable plain-text reply draft from the model output, else None to fall back."""
    if not text or not text.strip():
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) >= 2 else cleaned.strip("`")
        cleaned = cleaned.strip()
    return cleaned or None


def completed_qa_draft_output(payload: dict[str, Any]) -> dict[str, Any]:
    """Build the Q&A reply-draft output, via the gateway when configured.

    Falls back to the backend-provided deterministic draft when no gateway is configured or the
    model returns nothing usable, so the job always completes and the inbox always has a suggestion.
    """
    fallback = payload.get("deterministicFallback") if isinstance(payload.get("deterministicFallback"), dict) else {}

    def _fallback_output() -> dict[str, Any]:
        return {
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
