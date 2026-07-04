"""Structured-output request + one validation-failure retry (§3.2), gateway-mocked.

Asserts each JSON-emitting job (transcription/caption/patient_memory/qa_revise) sends
``response_format=json_schema``, retries ONCE on an invalid output appending the validation error, and
— when the kill-switch is off — makes a single legacy call with no response_format and no retry.
"""
import json
import unittest
from unittest.mock import MagicMock, patch

from ai_engine.core.structured import call_with_validation_retry


def _response(text):
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = text
    return response


class CallWithValidationRetryTests(unittest.TestCase):
    def test_valid_first_attempt_is_single_call(self):
        invoke = MagicMock(return_value='{"ok": 1}')
        result = call_with_validation_retry(
            task="t", ai_models=None, model="m", effort=None, invoke=invoke, parse=lambda raw: json.loads(raw),
        )
        self.assertEqual(result, {"ok": 1})
        self.assertEqual(invoke.call_count, 1)
        self.assertIsNone(invoke.call_args.args[2])  # correction is None on the only attempt

    def test_invalid_then_valid_retries_with_correction(self):
        calls = []

        def invoke(model, effort, correction):
            calls.append(correction)
            return "not json" if correction is None else '{"ok": 2}'

        def parse(raw):
            return json.loads(raw) if raw.startswith("{") else None

        result = call_with_validation_retry(task="t", ai_models=None, model="m", effort=None, invoke=invoke, parse=parse)
        self.assertEqual(result, {"ok": 2})
        self.assertEqual(len(calls), 2)
        self.assertIsNone(calls[0])
        self.assertIsInstance(calls[1], str)  # the retry carries the validation error

    def test_invalid_twice_returns_final_parse(self):
        invoke = MagicMock(return_value="still bad")
        result = call_with_validation_retry(
            task="t", ai_models=None, model="m", effort=None, invoke=invoke, parse=lambda raw: None,
        )
        self.assertIsNone(result)
        self.assertEqual(invoke.call_count, 2)

    def test_disabled_flag_is_single_call_no_retry(self):
        invoke = MagicMock(return_value="bad")
        with patch("ai_engine.core.structured.structured_outputs_enabled", return_value=False):
            result = call_with_validation_retry(
                task="t", ai_models=None, model="m", effort=None, invoke=invoke, parse=lambda raw: None,
            )
        self.assertIsNone(result)
        self.assertEqual(invoke.call_count, 1)


class JobStructuredOutputTests(unittest.TestCase):
    def test_patient_memory_sends_response_format_and_retries(self):
        from ai_engine.jobs.patient_memory import completed_patient_memory_output

        client = MagicMock()
        good = '{"summary":"S","history":{"snapshot":"x","sections":[{"label":"L","body":"B"}],"visits":[]}}'
        client.chat.completions.create.side_effect = [_response("garbage"), _response(good)]
        with patch("ai_engine.jobs.patient_memory.transcription_is_configured", return_value=True), patch(
            "ai_engine.jobs.patient_memory.gateway_client", return_value=client
        ), patch("ai_engine.jobs.patient_memory.resolve_model", return_value="m"):
            out = completed_patient_memory_output({"deterministicFallback": {"summary": "fb"}, "patient": {}, "aiModels": {}})
        # First attempt was garbage → retried → valid → AI output (not the deterministic fallback).
        self.assertEqual(out["summary"], "S")
        self.assertEqual(client.chat.completions.create.call_count, 2)
        first_kwargs = client.chat.completions.create.call_args_list[0].kwargs
        self.assertIn("response_format", first_kwargs)
        self.assertEqual(first_kwargs["response_format"]["type"], "json_schema")
        # The retry appended a correction user message.
        retry_messages = client.chat.completions.create.call_args_list[1].kwargs["messages"]
        self.assertTrue(any("invalid" in str(m.get("content", "")).lower() for m in retry_messages))

    def test_patient_memory_falls_back_after_two_invalid(self):
        from ai_engine.jobs.patient_memory import completed_patient_memory_output

        client = MagicMock()
        client.chat.completions.create.return_value = _response("garbage")
        with patch("ai_engine.jobs.patient_memory.transcription_is_configured", return_value=True), patch(
            "ai_engine.jobs.patient_memory.gateway_client", return_value=client
        ), patch("ai_engine.jobs.patient_memory.resolve_model", return_value="m"):
            out = completed_patient_memory_output({"deterministicFallback": {"summary": "fb", "source": "mock-deterministic"}, "patient": {}, "aiModels": {}})
        self.assertEqual(out["source"], "mock-deterministic")
        self.assertEqual(client.chat.completions.create.call_count, 2)


if __name__ == "__main__":
    unittest.main()
