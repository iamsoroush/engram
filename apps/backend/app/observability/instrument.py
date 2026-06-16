"""Prometheus instrumentation for the FastAPI app.

Exposes ``/metrics`` (NOT under the API prefix — Prometheus scrapes ``backend:8000/metrics`` on the
internal Docker network). Default instrumentation provides ``http_requests_total{...}`` and
request-duration histograms used by the dashboard + APIHighErrorRate / APIHighLatency alerts.
"""
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator


def instrument(app: FastAPI) -> None:
    """Attach Prometheus instrumentation and mount ``/metrics`` on the app.

    Args:
        app: The FastAPI application to instrument.
    """
    Instrumentator(
        should_group_status_codes=False,
        # Keep the high-cardinality scrape endpoint itself out of the metrics.
        excluded_handlers=["/metrics"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
