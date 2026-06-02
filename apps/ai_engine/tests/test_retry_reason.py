import unittest

from ai_engine.tasks import retry_reason_for_exception


class RetryReasonTests(unittest.TestCase):
    def test_audio_source_missing_is_retryable_source_missing(self):
        reason = retry_reason_for_exception(RuntimeError("Audio capture source file is missing"))

        self.assertEqual(reason, "source_missing")

    def test_conversion_failure_is_classified(self):
        reason = retry_reason_for_exception(RuntimeError("Audio conversion to FLAC failed: invalid data"))

        self.assertEqual(reason, "conversion_failed")

    def test_transcription_timeout_is_gateway_unavailable(self):
        reason = retry_reason_for_exception(RuntimeError("Audio transcription gateway timeout"))

        self.assertEqual(reason, "gateway_unavailable")


if __name__ == "__main__":
    unittest.main()
