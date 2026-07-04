"""Typed worker exceptions → backend retry-reason codes (§3.6).

Each failure is raised at the seam that KNOWS the cause (backend 404 → SourceMissing; ffmpeg →
ConversionFailed; gateway transport → GatewayUnavailable; output-schema validation exhausted →
InvalidOutput), carrying its ``retry_reason``. ``retry_reason_for_exception`` maps type → code
exhaustively, replacing the old brittle substring matcher. All subclass ``RuntimeError`` so existing
``RuntimeError``-shaped call sites and their messages are unchanged.

Reason codes (all RETRYABLE): ``source_missing``, ``conversion_failed``, ``gateway_unavailable``,
``invalid_output`` (new — model returned malformed/unusable output, distinct from a gateway outage),
``worker_error`` (unclassified). Gateway-down stays retryable-then-durable; fair-use parking stays
backend-owned — the worker never learns about budgets.
"""
from __future__ import annotations

import httpx
import openai


class WorkerError(RuntimeError):
    """Base worker failure. Subclasses carry the backend retry-reason code they map to."""

    retry_reason = "worker_error"


class SourceMissing(WorkerError):
    """A required source artifact (capture media, voice note) is absent (backend 404 / missing content)."""

    retry_reason = "source_missing"


class ConversionFailed(WorkerError):
    """Media conversion failed (ffmpeg missing / bad input)."""

    retry_reason = "conversion_failed"


class GatewayUnavailable(WorkerError):
    """The AI gateway is unreachable or not configured (transport error / blank base_url)."""

    retry_reason = "gateway_unavailable"


class InvalidOutput(WorkerError):
    """The model returned malformed/unusable output that failed schema/contract validation."""

    retry_reason = "invalid_output"


def retry_reason_for_exception(exc: Exception) -> str:
    """Map a worker exception to its backend retry-reason code (type-based, exhaustive)."""
    if isinstance(exc, WorkerError):
        return exc.retry_reason
    # Library exceptions raised below our own seams: a backend file 404 is a missing source; any gateway
    # or backend transport failure is a (retryable) availability problem.
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return "source_missing"
    if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException)):
        return "gateway_unavailable"
    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError, openai.APIError)):
        return "gateway_unavailable"
    return "worker_error"
