"""Q&A reply voice-edit job (AES-402): revise-or-replace a draft reply from the doctor's voice note.

The model decides whether the spoken note revises the current draft or dictates an entirely new
reply, then produces the final text. The doctor approves before anything is sent, so it invents no
clinical facts beyond the draft + spoken note + context. Falls back to keeping the current draft
unchanged when gateway-less / no audio / unusable output.
"""
from typing import Any

from ai_engine.contracts.qa import (  # noqa: F401
    QA_REVISE_OUTPUT_VERSION,
    parse_qa_revise_output,
    qa_revise_json_schema,
)
from ai_engine.core.backend_client import BackendClient
from ai_engine.core.gateway import gateway_client, resolve_model, transcription_is_configured
from ai_engine.core.media import audio_to_flac_mono_16khz_base64
from ai_engine.core.structured import (
    call_with_validation_retry,
    correction_message,
    response_format,
    structured_outputs_enabled,
)
from ai_engine.core.util import utc_now
# The prompt lives in its own versioned module (§3.3); ``qa_revise_prompt`` is re-exported for the shim
# + tests, and the envelope stamps ``QA_REVISE_PROMPT_VERSION``.
from ai_engine.prompts.qa_revise import PROMPT_VERSION as QA_REVISE_PROMPT_VERSION
from ai_engine.prompts.qa_revise import build as qa_revise_prompt  # noqa: F401


def completed_qa_revise_output(payload: dict[str, Any], audio: bytes) -> dict[str, Any]:
    """Revise/replace the reply from the doctor's voice note via the configured Q&A model.

    Falls back to keeping the current draft unchanged when no gateway is configured or the model
    returns nothing usable, so the job always completes (the doctor can still edit by hand).
    """
    fallback = payload.get("deterministicFallback") if isinstance(payload.get("deterministicFallback"), dict) else {}

    def _fallback_output() -> dict[str, Any]:
        return {
            "schemaVersion": QA_REVISE_OUTPUT_VERSION,
            "promptVersion": QA_REVISE_PROMPT_VERSION,
            "mode": fallback.get("mode") or "revise",
            "reply": fallback.get("reply"),
            "source": fallback.get("source") or "mock-deterministic",
            "generated_by": "ai-engine",
            "generated_at": utc_now().isoformat(),
        }

    if not transcription_is_configured() or not audio:
        return _fallback_output()

    ai_models = payload.get("aiModels") if isinstance(payload.get("aiModels"), dict) else None
    model = resolve_model("qa_draft", ai_models)
    base64_flac = audio_to_flac_mono_16khz_base64(audio)
    client = gateway_client("qa_draft")

    def invoke(call_model: str, _effort: str | None, correction: str | None) -> str:
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": qa_revise_prompt(payload)},
                    {"type": "input_audio", "input_audio": {"data": base64_flac, "format": "audio/flac"}},
                ],
            }
        ]
        request: dict[str, Any] = {"model": call_model, "messages": messages}
        if structured_outputs_enabled():
            request["response_format"] = response_format("qa_revise_output", qa_revise_json_schema())
        if correction is not None:
            messages.append(correction_message(correction))
        # A gateway/network error propagates and is retried by the task wrapper.
        response = client.chat.completions.create(**request)
        return response.choices[0].message.content or ""

    parsed = call_with_validation_retry(
        task="qa_draft", ai_models=ai_models, model=model, effort=None, invoke=invoke, parse=parse_qa_revise_output,
    )
    if parsed is None:
        return _fallback_output()
    return {
        "schemaVersion": QA_REVISE_OUTPUT_VERSION,
        "promptVersion": QA_REVISE_PROMPT_VERSION,
        "mode": parsed["mode"],
        "reply": parsed["reply"],
        "source": f"ai:{model}",
        "model": model,
        "generated_by": "ai-engine",
        "generated_at": utc_now().isoformat(),
    }


def run_qa_revise_job(job_id: str, *, celery_task_id: str | None, retry_count: int) -> None:
    """Run a Q&A reply voice-edit job (revise/replace from the doctor's spoken note; AES-402)."""
    client = BackendClient()
    payload = client.start_job(job_id, celery_task_id=celery_task_id, retry_count=retry_count)
    job = payload["job"]
    if job.get("status") == "succeeded":
        return
    qa = payload.get("qaRevise") if isinstance(payload.get("qaRevise"), dict) else {}
    audio = b""
    endpoint = qa.get("voiceEndpoint")
    if transcription_is_configured() and endpoint:
        audio, _ = client.get_file(endpoint)
    client.complete_job(job_id, output_key="qa_revise", output=completed_qa_revise_output(payload, audio))
