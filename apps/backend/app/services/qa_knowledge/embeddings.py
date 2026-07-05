"""Optional embeddings-gateway client for Q&A knowledge retrieval.

The embedding half of hybrid retrieval. When ``BACKEND_EMBEDDINGS_BASE_URL`` is set the backend calls
an OpenAI-compatible ``/embeddings`` endpoint (via the stdlib — no new dependency, no OpenAI SDK on the
backend); when it is blank, embeddings are DISABLED and retrieval runs lexical-only, so dev / CI / e2e
stay deterministic and gateway-less. Every failure degrades to ``None`` (retrieval falls back to
lexical) — embedding must never break drafting.

Boundary note: this is the ONE place the backend talks to an AI gateway directly. It is a narrow,
optional read used to build the retrieval payload; the qa_draft/qa_revise *generation* stays in the
worker. Secrets live in env only (never the DB), like the worker's gateway config.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from app.config import settings

logger = logging.getLogger(__name__)


def embeddings_configured() -> bool:
    """Whether an embeddings gateway is configured (else retrieval is lexical-only)."""
    return bool((settings.embeddings_base_url or "").strip())


def _endpoint() -> str:
    base = (settings.embeddings_base_url or "").strip().rstrip("/")
    return f"{base}/embeddings"


def embed_text(text: str) -> list[float] | None:
    """Embed one short text via the gateway; ``None`` when unconfigured or on any failure.

    Kept resilient by design: a gateway outage or malformed response silently yields ``None`` so the
    caller ranks lexically — an embedding is an enhancement, never a hard dependency of a reply draft.
    """
    if not embeddings_configured():
        return None
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    payload = json.dumps({"model": settings.embeddings_model, "input": cleaned}).encode("utf-8")
    request = urllib.request.Request(
        _endpoint(),
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.embeddings_api_key}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.embeddings_timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:  # noqa: BLE001
        logger.warning("Q&A embeddings call failed; falling back to lexical-only retrieval: %s", exc)
        return None
    return _parse_embedding(body)


def _parse_embedding(body: object) -> list[float] | None:
    """Pull the vector out of an OpenAI-style embeddings response; ``None`` if the shape is off."""
    if not isinstance(body, dict):
        return None
    data = body.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        return None
    vector = data[0].get("embedding")
    if not isinstance(vector, list) or not vector:
        return None
    try:
        return [float(component) for component in vector]
    except (TypeError, ValueError):
        return None
