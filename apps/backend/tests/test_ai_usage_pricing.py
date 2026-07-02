"""Fair-use metering pricing math — turns real gateway usage records into cost.

Locks the two pricing paths: transcription is per audio-minute (measured
gemini-3.1-flash-lite $0.0021/min); LLM/vision is per token (gpt-5.4-nano $0.20/$1.25 per 1M).
"""
import unittest

from app.services.ai_usage.pricing import (
    audio_seconds_from_records,
    usage_record_cost_usd,
    usage_records_cost_micros,
)


class PricingTests(unittest.TestCase):
    def test_transcription_priced_per_audio_minute(self):
        # 60s of gemini-3.1-flash-lite = exactly $0.0021.
        rec = {"task": "transcription", "model": "gemini-3.1-flash-lite", "audioSeconds": 60}
        self.assertAlmostEqual(usage_record_cost_usd(rec), 0.0021, places=6)

    def test_transcription_falls_back_to_audio_tokens(self):
        # No measured seconds → derive from prompt tokens at ~32 tok/s (1920 tok ≈ 60s).
        rec = {"task": "transcription", "model": "gemini-3.1-flash-lite", "promptTokens": 1920}
        self.assertAlmostEqual(usage_record_cost_usd(rec), 0.0021, places=6)

    def test_llm_priced_per_token(self):
        # gpt-5.4-nano: 1e6 input @ $0.20 + 1e6 output @ $1.25 = $1.45.
        rec = {"task": "report_synthesis", "model": "gpt-5.4-nano", "promptTokens": 1_000_000, "completionTokens": 1_000_000}
        self.assertAlmostEqual(usage_record_cost_usd(rec), 1.45, places=6)

    def test_unknown_model_uses_default_llm_rate(self):
        rec = {"task": "caption", "model": "some-future-model", "promptTokens": 1_000_000, "completionTokens": 0}
        self.assertAlmostEqual(usage_record_cost_usd(rec), 0.20, places=6)

    def test_records_cost_micros_sums_and_rounds(self):
        records = [
            {"task": "transcription", "model": "gemini-3.1-flash-lite", "audioSeconds": 120},  # $0.0042
            {"task": "report_synthesis", "model": "gpt-5.4-nano", "promptTokens": 3000, "completionTokens": 1000},  # 3000*.2/1e6 + 1000*1.25/1e6
        ]
        expected = 0.0042 + (3000 * 0.20 + 1000 * 1.25) / 1_000_000
        self.assertEqual(usage_records_cost_micros(records), int(round(expected * 1_000_000)))

    def test_audio_seconds_from_records(self):
        records = [
            {"task": "transcription", "model": "x", "audioSeconds": 30},
            {"task": "report_synthesis", "model": "y", "promptTokens": 10},
            {"task": "transcription", "model": "x", "audioSeconds": 45},
        ]
        self.assertEqual(audio_seconds_from_records(records), 75)

    def test_empty_records_zero(self):
        self.assertEqual(usage_records_cost_micros([]), 0)
        self.assertEqual(usage_records_cost_micros(None), 0)


if __name__ == "__main__":
    unittest.main()
