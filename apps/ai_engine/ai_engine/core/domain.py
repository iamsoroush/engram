"""The vertical-agnostic prompt-framing seam.

Every worker prompt reads its clinical framing from the backend-supplied ``domain`` descriptor
(``app/services/verticals.py:domain_descriptor``) rather than hardcoding a vertical, so the same
worker serves aesthetics, therapy, dermatology, … See ``docs/ai_engine/README.md``.
"""
from typing import Any


def domain_framing(context: dict[str, Any] | None) -> tuple[str, list[str], list[str]]:
    """Extract vertical-aware prompt framing from a job context/payload.

    Vertical-AGNOSTIC by contract: the backend supplies a `domain` descriptor
    (`app/services/verticals.py:domain_descriptor`) carrying the setting `label` and optional
    `vocabulary` / `captionFindings` hints. When it is absent this returns a neutral "clinic"
    default with no vocabulary — so a worker prompt NEVER hardcodes or assumes a vertical. Any
    vertical-specific wording must come through this descriptor (i.e. be optional + data-driven).
    """
    domain = context.get("domain") if isinstance(context, dict) and isinstance(context.get("domain"), dict) else {}
    raw_label = domain.get("label")
    label = raw_label.strip() if isinstance(raw_label, str) and raw_label.strip() else "clinic"
    vocabulary = [value for value in (domain.get("vocabulary") or []) if isinstance(value, str)]
    caption_findings = [value for value in (domain.get("captionFindings") or []) if isinstance(value, str)]
    return label, vocabulary, caption_findings
