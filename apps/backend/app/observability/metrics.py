"""Custom Prometheus counters for product-critical events.

The default HTTP metrics (``http_requests_total`` + request-duration histograms) come from
``prometheus-fastapi-instrumentator`` (wired in :func:`app.observability.instrument`). The
counters here are the product-critical signals referenced by name in
``monitoring/prometheus/alert.rules.yml`` (FailedUploadsSpike, AIJobFailureRate), so their names
must not change without updating those rules.
"""
from prometheus_client import Counter

# Incremented on the server-side error path of a capture upload (capture-first promise).
capture_uploads_failed_total = Counter(
    "engram_capture_uploads_failed_total",
    "Capture uploads that failed server-side.",
)

# Incremented on AI-job completion/failure, labelled by terminal status.
ai_jobs_total = Counter(
    "engram_ai_jobs_total",
    "AI processing jobs by terminal status.",
    ["status"],
)


def record_capture_upload_failed() -> None:
    """Count one failed capture upload."""
    capture_uploads_failed_total.inc()


def record_ai_job(status: str) -> None:
    """Count one AI job reaching a terminal state.

    Args:
        status: Terminal status label, e.g. ``"succeeded"`` or ``"failed"``.
    """
    ai_jobs_total.labels(status=status).inc()
