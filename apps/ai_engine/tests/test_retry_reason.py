"""Retry-reason mapping is TYPE-based (§3.6), not substring-based.

Each typed worker exception carries its reason code; library transport errors map to availability; a
raw/unknown exception falls back to ``worker_error``. The new ``invalid_output`` code separates
model-output failures from gateway outages in observability.
"""
import unittest

import httpx

from ai_engine.core.errors import (
    ConversionFailed,
    GatewayUnavailable,
    InvalidOutput,
    SourceMissing,
    WorkerError,
)
from ai_engine.tasks import retry_reason_for_exception


class RetryReasonTests(unittest.TestCase):
    def test_typed_exceptions_carry_their_reason(self):
        self.assertEqual(retry_reason_for_exception(SourceMissing("x")), "source_missing")
        self.assertEqual(retry_reason_for_exception(ConversionFailed("x")), "conversion_failed")
        self.assertEqual(retry_reason_for_exception(GatewayUnavailable("x")), "gateway_unavailable")
        self.assertEqual(retry_reason_for_exception(InvalidOutput("x")), "invalid_output")
        self.assertEqual(retry_reason_for_exception(WorkerError("x")), "worker_error")

    def test_typed_exceptions_are_runtime_errors(self):
        # Subclassing RuntimeError keeps every existing RuntimeError-shaped call site + assertion valid.
        for exc in (SourceMissing, ConversionFailed, GatewayUnavailable, InvalidOutput, WorkerError):
            self.assertTrue(issubclass(exc, RuntimeError))

    def test_backend_file_404_is_source_missing(self):
        request = httpx.Request("GET", "http://backend/internal/captures/1/file-content")
        response = httpx.Response(404, request=request)
        exc = httpx.HTTPStatusError("404", request=request, response=response)
        self.assertEqual(retry_reason_for_exception(exc), "source_missing")

    def test_transport_errors_are_gateway_unavailable(self):
        self.assertEqual(retry_reason_for_exception(httpx.ConnectError("down")), "gateway_unavailable")
        self.assertEqual(
            retry_reason_for_exception(httpx.TimeoutException("slow")), "gateway_unavailable"
        )

    def test_unknown_exception_is_worker_error(self):
        # No substring games: a message that merely MENTIONS "timeout" no longer flips the reason.
        self.assertEqual(retry_reason_for_exception(RuntimeError("some timeout mention")), "worker_error")
        self.assertEqual(retry_reason_for_exception(ValueError("boom")), "worker_error")


if __name__ == "__main__":
    unittest.main()
