"""Shared prompt building blocks — the single home for cross-job framing (§3.3).

Per-job prompt modules read their vertical framing + language discipline from here (which re-exports
the vertical-agnostic seam ``core.domain`` and the language directives ``core.text``), so a discipline
fix lands once and the per-job files hold only their own framing. ``vocabulary_line`` is the literal
vocab hint shared byte-for-byte by the transcription and synthesis prompts.
"""
from __future__ import annotations

from ai_engine.core.domain import domain_framing  # noqa: F401 — re-exported as the shared framing seam
from ai_engine.core.text import (  # noqa: F401 — re-exported as the shared language directives
    enrichment_language_directive,
    transcription_language_directive,
)


def vocabulary_line(label: str, vocabulary: list[str]) -> str:
    """The ``Common <label> vocabulary may include …`` hint (shared verbatim by transcription+synthesis)."""
    return f"Common {label} vocabulary may include {', '.join(vocabulary)}. " if vocabulary else ""
