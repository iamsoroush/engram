"""Shared worker infrastructure for the AI engine.

The ``core`` package holds the cross-job seams — gateway client + usage metering, the backend HTTP
client, media conversion, text/language helpers, the vertical-agnostic domain framing, and the
deterministic fixture recognition. Job runners under ``ai_engine.jobs`` compose these; nothing in
``core`` imports a job or the backend (see ``docs/ai_engine/README.md`` for the boundary rule).
"""
