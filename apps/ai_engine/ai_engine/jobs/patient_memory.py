"""Combined patient memory job (Pro): longitudinal summary + history in one grounded call.

Updates the patient's memory from the prior memory + new visit briefs, quoting doses verbatim and
inventing nothing. Falls back to the backend-provided deterministic content when no gateway is
configured or the model returns something unusable, so the job always completes with valid memory.
Vertical-agnostic via the domain descriptor.
"""
from typing import Any

from ai_engine.contracts.memory import (  # noqa: F401 — re-exported for the processing shim + tests
    PATIENT_MEMORY_OUTPUT_VERSION,
    parse_patient_memory_output,
    patient_memory_json_schema,
)
from ai_engine.core.backend_client import BackendClient
from ai_engine.core.gateway import gateway_client, resolve_model, transcription_is_configured
from ai_engine.core.structured import (
    call_with_validation_retry,
    correction_message,
    response_format,
    structured_outputs_enabled,
)
from ai_engine.core.util import utc_now
# The prompt lives in its own versioned module (§3.3); ``patient_memory_prompt`` is re-exported for the
# shim + tests, and the envelope stamps ``PATIENT_MEMORY_PROMPT_VERSION``.
from ai_engine.prompts.patient_memory import PROMPT_VERSION as PATIENT_MEMORY_PROMPT_VERSION
from ai_engine.prompts.patient_memory import build as patient_memory_prompt  # noqa: F401


def completed_patient_memory_output(payload: dict[str, Any]) -> dict[str, Any]:
    """Build the combined patient summary+history output, via the gateway when configured.

    Falls back to the backend-provided deterministic content when no gateway is configured or when
    the model returns something unusable, so the job always completes with valid memory.
    """
    fallback = payload.get("deterministicFallback") if isinstance(payload.get("deterministicFallback"), dict) else {}

    def _fallback_output() -> dict[str, Any]:
        return {
            "schemaVersion": PATIENT_MEMORY_OUTPUT_VERSION,
            "promptVersion": PATIENT_MEMORY_PROMPT_VERSION,
            "summary": fallback.get("summary"),
            "history": fallback.get("history"),
            "card": fallback.get("card"),
            "source": fallback.get("source") or "mock-deterministic",
            "generated_by": "ai-engine",
            "generated_at": utc_now().isoformat(),
        }

    if not transcription_is_configured():
        return _fallback_output()

    ai_models = payload.get("aiModels") if isinstance(payload.get("aiModels"), dict) else None
    model = resolve_model("patient_memory", ai_models)
    client = gateway_client("patient_memory")

    def invoke(call_model: str, _effort: str | None, correction: str | None) -> str:
        messages: list[dict[str, Any]] = [{"role": "user", "content": patient_memory_prompt(payload)}]
        request: dict[str, Any] = {"model": call_model, "messages": messages}
        if structured_outputs_enabled():
            request["response_format"] = response_format("patient_memory_output", patient_memory_json_schema())
        if correction is not None:
            messages.append(correction_message(correction))
        # A gateway/network error propagates and is retried by the task wrapper (gateway_unavailable).
        response = client.chat.completions.create(**request)
        return response.choices[0].message.content or ""

    parsed = call_with_validation_retry(
        task="patient_memory", ai_models=ai_models, model=model, effort=None,
        invoke=invoke, parse=parse_patient_memory_output,
    )
    if parsed is None:
        return _fallback_output()
    history = parsed["history"]
    history["source"] = f"ai:{model}"
    return {
        "schemaVersion": PATIENT_MEMORY_OUTPUT_VERSION,
        "promptVersion": PATIENT_MEMORY_PROMPT_VERSION,
        "summary": parsed["summary"],
        "history": history,
        # Carry the model's compact card through; backend coerces it + falls back deterministically.
        "card": parsed.get("card") or fallback.get("card"),
        "source": f"ai:{model}",
        "model": model,
        "generated_by": "ai-engine",
        "generated_at": utc_now().isoformat(),
    }


def run_patient_memory_job(job_id: str, *, celery_task_id: str | None, retry_count: int) -> None:
    """Run a combined patient summary+history job through the backend API contract."""
    client = BackendClient()
    payload = client.start_job(job_id, celery_task_id=celery_task_id, retry_count=retry_count)
    job = payload["job"]
    if job.get("status") == "succeeded":
        return
    client.complete_job(job_id, output_key="patient_memory", output=completed_patient_memory_output(payload))
