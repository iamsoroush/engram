"""Note capture job: a pure passthrough (no gateway call, no decoration).

A note is marked processed with its RAW text under ``note_text`` — the report itself reads the raw
``detail``, so the envelope only carries provenance + chain ordering. See ``run_capture_processing_job``.
"""
from typing import Any


def raw_note_text(capture: dict[str, Any]) -> str | None:
    """Return the captured note's raw text (the passthrough's processed text), or None when empty."""
    metadata = capture.get("metadata") if isinstance(capture.get("metadata"), dict) else {}
    detail = str(metadata.get("detail") or "").strip()
    return detail or None
