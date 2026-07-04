"""Combined patient memory job (Pro): longitudinal summary + history in one grounded call.

Updates the patient's memory from the prior memory + new visit briefs, quoting doses verbatim and
inventing nothing. Falls back to the backend-provided deterministic content when no gateway is
configured or the model returns something unusable, so the job always completes with valid memory.
Vertical-agnostic via the domain descriptor.
"""
import json
from typing import Any

from ai_engine.contracts.memory import (  # noqa: F401 — re-exported for the processing shim + tests
    PATIENT_MEMORY_OUTPUT_VERSION,
    parse_patient_memory_output,
)
from ai_engine.core.backend_client import BackendClient
from ai_engine.core.domain import domain_framing
from ai_engine.core.gateway import gateway_client, resolve_model, transcription_is_configured
from ai_engine.core.util import utc_now


def patient_memory_prompt(payload: dict[str, Any]) -> str:
    """Build the prompt for the combined patient summary + history (incremental, grounded)."""
    patient = payload.get("patient") if isinstance(payload.get("patient"), dict) else {}
    language = payload.get("language")
    label, _, _ = domain_framing(payload)  # vertical-aware; neutral "clinic" when absent
    language_directive = (
        f"Write EVERY field in {language} and ONLY {language} — one language throughout, native script."
        if isinstance(language, str) and language.strip()
        else (
            "Write EVERY field in the SAME language the visit notes use (if the notes are Persian/Farsi, "
            "write Persian — do NOT default to English) — one language throughout, native script."
        )
    )
    return "\n\n".join(
        (
            "You are Engram, a calm clinical assistant that maintains a patient's longitudinal memory. "
            f"The clinical setting is a {label}.",
            (
                "Update this patient's memory from the prior memory and the new visit briefs below. "
                "Each visit brief may include the treatments performed that visit (product, dose, area, "
                "lot) — use them to ground recall in specifics (e.g. 'last visit: Voluma 0.3 mL, left "
                "cheek'), quoting doses verbatim. Produce a warm, assistant-voiced brief — natural "
                "sentences, never a form or bullet dump. Synthesize across visits, but do NOT invent "
                "clinical facts, names, products, or doses that are not present in the briefs. Do NOT "
                "include the patient's name in any field — it is already shown beside this text in the "
                "UI; use pronouns or omit the subject. Keep the card summary to 1-2 sentences. "
                "Also produce a compact 'card' for the line-up worklist: 'storySoFar' and 'rightNow' are "
                "EACH at most 2 short sentences; 'flags' surfaces only genuinely important "
                "allergy/consent/preference/caution items actually found in the briefs — return an empty "
                "list when there are none, and never invent one. "
                f"{language_directive} "
                "The whole brief MUST be in that one language — NEVER mix (e.g. an English sentence "
                "containing «گونه چپ»). Brand names and lot numbers may keep their original form. When "
                "the language is Persian/Farsi, embedding common English clinical terms is fine "
                "(Finglish, e.g. «فیلر گونه چپ»), but do not switch into English sentences and never "
                "romanize Persian into Latin."
            ),
            (
                "Return ONLY strict JSON (no markdown, no code fences) with EXACTLY this shape:\n"
                '{"summary": "<1-2 sentence card summary>", '
                '"history": {"snapshot": "<one line: patient + current focus>", '
                '"sections": [{"label": "Story so far", "body": "<2-4 sentences>"}, '
                '{"label": "Worth remembering", "body": "<preferences, cautions, recurring themes>"}, '
                '{"label": "Right now", "body": "<open threads / next visit>"}], "visits": []}, '
                '"card": {"storySoFar": "<at most 2 short sentences>", '
                '"rightNow": "<at most 2 short sentences: what is open / next visit>", '
                '"flags": [{"kind": "allergy|consent|preference|caution", "label": "<short>"}]}}'
            ),
            f"Patient context:\n{json.dumps(patient, ensure_ascii=False, sort_keys=True)}",
        )
    )


def completed_patient_memory_output(payload: dict[str, Any]) -> dict[str, Any]:
    """Build the combined patient summary+history output, via the gateway when configured.

    Falls back to the backend-provided deterministic content when no gateway is configured or when
    the model returns something unusable, so the job always completes with valid memory.
    """
    fallback = payload.get("deterministicFallback") if isinstance(payload.get("deterministicFallback"), dict) else {}

    def _fallback_output() -> dict[str, Any]:
        return {
            "schemaVersion": PATIENT_MEMORY_OUTPUT_VERSION,
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
    # A gateway/network error propagates and is retried by the task wrapper (gateway_unavailable).
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": patient_memory_prompt(payload)}],
    )
    parsed = parse_patient_memory_output(response.choices[0].message.content or "")
    if parsed is None:
        return _fallback_output()
    history = parsed["history"]
    history["source"] = f"ai:{model}"
    return {
        "schemaVersion": PATIENT_MEMORY_OUTPUT_VERSION,
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
