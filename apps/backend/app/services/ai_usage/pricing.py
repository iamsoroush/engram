"""AI provider pricing — the single source of truth for turning real gateway usage into cost.

Rates are the owner-supplied provider rates that the self-hosted gateway (gw.engram.ir) bills against
(the gateway adds no per-token cost). LLM/vision tasks are priced per token; transcription is priced
per audio-minute. Confirmed live 2026-07-02: transcription `gemini-3.1-flash-lite`, synthesis
`gpt-5.4-nano`. Change a rate here and the whole meter recomputes.

Cost is computed in micro-dollars (int) to avoid float drift in the accumulator.
"""
from __future__ import annotations

from typing import Any

# ($/1M input tokens, $/1M output tokens) for chat/vision LLM tasks, by model id.
LLM_TOKEN_RATES_USD_PER_M: dict[str, tuple[float, float]] = {
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.4-mini": (0.40, 1.60),
    "gpt-5.4": (2.00, 8.00),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-3.1-flash-lite": (0.10, 0.40),
}
_DEFAULT_LLM_RATE = (0.20, 1.25)

# $/audio-minute for transcription, by model id.
TRANSCRIPTION_RATE_USD_PER_MIN: dict[str, float] = {
    "gemini-3.1-flash-lite": 0.0021,
    "gemini-3.5-flash": 0.0098,
    "gemini-2.5-flash": 0.0098,
}
_DEFAULT_TRANSCRIPTION_RATE = 0.0021

# Fallback when a transcription record has no measured audioSeconds: Gemini bills audio at ~32
# tokens/second, so seconds ≈ audio/prompt tokens ÷ 32.
_AUDIO_TOKENS_PER_SECOND = 32.0


def _llm_rate(model: str | None) -> tuple[float, float]:
    return LLM_TOKEN_RATES_USD_PER_M.get(model or "", _DEFAULT_LLM_RATE)


def _transcription_rate(model: str | None) -> float:
    return TRANSCRIPTION_RATE_USD_PER_MIN.get(model or "", _DEFAULT_TRANSCRIPTION_RATE)


def usage_record_cost_usd(record: dict[str, Any]) -> float:
    """Cost (USD) of one gateway call from its metered usage record.

    Record shape (from the worker): {task, model, promptTokens, completionTokens, audioSeconds?}.
    Transcription is priced per audio-minute; everything else per token.
    """
    task = record.get("task")
    model = record.get("model")
    prompt_tokens = int(record.get("promptTokens") or 0)
    completion_tokens = int(record.get("completionTokens") or 0)
    if task == "transcription":
        seconds = record.get("audioSeconds")
        if seconds is None:
            seconds = prompt_tokens / _AUDIO_TOKENS_PER_SECOND if prompt_tokens else 0.0
        return (float(seconds) / 60.0) * _transcription_rate(model)
    rate_in, rate_out = _llm_rate(model)
    return (prompt_tokens * rate_in + completion_tokens * rate_out) / 1_000_000.0


def usage_records_cost_micros(records: list[dict[str, Any]] | None) -> int:
    """Total cost of a job's gateway calls, in micro-dollars (int)."""
    if not records:
        return 0
    total = sum(usage_record_cost_usd(record) for record in records)
    return int(round(total * 1_000_000))


def audio_seconds_from_records(records: list[dict[str, Any]] | None) -> int:
    """Total measured audio seconds across a job's transcription records (int)."""
    if not records:
        return 0
    total = 0.0
    for record in records:
        if record.get("task") == "transcription" and record.get("audioSeconds") is not None:
            total += float(record["audioSeconds"])
    return int(round(total))
