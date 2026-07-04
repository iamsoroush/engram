"""Q&A reply voice-edit job (AES-402): revise-or-replace a draft reply from the doctor's voice note.

The model decides whether the spoken note revises the current draft or dictates an entirely new
reply, then produces the final text. The doctor approves before anything is sent, so it invents no
clinical facts beyond the draft + spoken note + context. Falls back to keeping the current draft
unchanged when gateway-less / no audio / unusable output.
"""
import json
from typing import Any

from ai_engine.contracts.qa import QA_REVISE_OUTPUT_VERSION, parse_qa_revise_output  # noqa: F401
from ai_engine.core.backend_client import BackendClient
from ai_engine.core.gateway import gateway_client, resolve_model, transcription_is_configured
from ai_engine.core.media import audio_to_flac_mono_16khz_base64
from ai_engine.core.util import utc_now


def qa_revise_prompt(payload: dict[str, Any]) -> str:
    """Prompt for a Q&A reply voice edit: classify revise-vs-replace and produce the reply (AES-402).

    The doctor recorded a voice note while reviewing a draft reply. The model must decide whether the
    note is a *revision* of the current draft or an *entirely new reply*, then output the resulting
    reply. The doctor approves before anything is sent, so this is a suggestion — invent no clinical
    facts beyond the draft + spoken note + context.
    """
    qa = payload.get("qaRevise") if isinstance(payload.get("qaRevise"), dict) else {}
    return "\n\n".join(
        (
            "You are Engram, helping an aesthetics-clinic doctor edit a reply to a patient's question "
            "using a voice note they just recorded. The doctor reviews and approves before sending.",
            (
                "Decide from the VOICE NOTE whether the doctor is REVISING the current draft (e.g. "
                "'make it warmer', 'remove the part about ice', 'add that she should avoid sun') or "
                "dictating an ENTIRELY NEW reply. Then produce the final reply text in the patient's "
                "language. Keep the doctor's sign-off. Do NOT invent clinical facts, doses, or products "
                "not present in the current draft, the spoken note, or the context. "
                "Return STRICT JSON only: {\"mode\":\"revise\"|\"replace\",\"reply\":\"<final reply text>\"}."
            ),
            f"Patient question:\n{qa.get('patientQuestion', '')}",
            f"Current draft reply:\n{qa.get('currentDraft', '')}",
            f"This patient's context:\n{json.dumps(qa.get('patientContext', {}), ensure_ascii=False, sort_keys=True)}",
            f"The doctor's prior answers:\n{json.dumps(qa.get('priorAnswers', []), ensure_ascii=False, sort_keys=True)}",
        )
    )


def completed_qa_revise_output(payload: dict[str, Any], audio: bytes) -> dict[str, Any]:
    """Revise/replace the reply from the doctor's voice note via the configured Q&A model.

    Falls back to keeping the current draft unchanged when no gateway is configured or the model
    returns nothing usable, so the job always completes (the doctor can still edit by hand).
    """
    fallback = payload.get("deterministicFallback") if isinstance(payload.get("deterministicFallback"), dict) else {}

    def _fallback_output() -> dict[str, Any]:
        return {
            "schemaVersion": QA_REVISE_OUTPUT_VERSION,
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
    # A gateway/network error propagates and is retried by the task wrapper.
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": qa_revise_prompt(payload)},
                    {"type": "input_audio", "input_audio": {"data": base64_flac, "format": "audio/flac"}},
                ],
            }
        ],
    )
    parsed = parse_qa_revise_output(response.choices[0].message.content or "")
    if parsed is None:
        return _fallback_output()
    return {
        "schemaVersion": QA_REVISE_OUTPUT_VERSION,
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
