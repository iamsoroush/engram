"""Application observability: Prometheus metrics + (optional) Sentry/GlitchTip error tracking.

All wiring here is purely additive and inert when unconfigured:
- :func:`instrument` mounts ``/metrics`` (default HTTP metrics) — always on (internal-network only).
- :func:`init_sentry` is a no-op when ``BACKEND_SENTRY_DSN`` is empty, so dev / Basic / unconfigured
  environments are unaffected.

Custom product counters live in :mod:`app.observability.metrics`.
"""
from app.observability.instrument import instrument
from app.observability.sentry import init_sentry

__all__ = ["instrument", "init_sentry"]
