"""Per-job worker runners.

One module per AI job (capture audio/photo/note, session synthesis, safety reconcile, patient
memory, Q&A draft/revise). Each composes the shared seams in ``ai_engine.core`` and drives its
lifecycle through ``BackendClient``. Jobs do not import each other — the one exception is
``session_synthesis`` calling ``safety_reconcile`` (its in-job second pass). See
``docs/ai_engine/README.md``.
"""
