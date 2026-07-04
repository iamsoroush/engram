"""Tiny cross-cutting primitives shared by every job family: UTC clock + confidence clamp.

These are dependency-free so any ``core`` or ``jobs`` module can import them without a cycle.
"""
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(timezone.utc)


def clamp_confidence(value: Any) -> float:
    """Clamp a model-provided confidence into [0.0, 1.0], defaulting to 0.0."""
    return max(0.0, min(float(value), 1.0)) if isinstance(value, int | float) else 0.0
