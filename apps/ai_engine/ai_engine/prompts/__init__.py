"""Auditable, versioned prompt modules (§3.3).

One module per prompt (``transcription``, ``caption``, ``synthesis``, ``safety_reconcile``,
``patient_memory``, ``qa_draft``, ``qa_revise``), each exposing ``PROMPT_VERSION`` +
``build(context) -> str``. Shared framing lives in ``_shared``. Every job stamps its prompt's
``PROMPT_VERSION`` into the output envelope (``promptVersion``) and the eval scorecard records it, so a
regression is attributable to a specific prompt diff. ``tests/test_prompt_versions`` hash-pins each
version: editing wording without bumping ``PROMPT_VERSION`` fails the suite. Per pipeline-versioning
D1, cache keys still ignore prompt version — provenance is recorded, never keyed on.

Prompt modules import only ``core``/``config``/``_shared`` (never ``jobs`` or backend code).
"""
