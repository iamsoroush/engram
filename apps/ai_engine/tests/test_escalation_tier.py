"""Escalation tier resolution + firing (§3.1).

The escalation tier (`aiModels[task].escalation`) is the "try harder" lever: a stronger model spent
only where the cheap tier just demonstrably failed — the validation-failure retry, or a backend
`escalate: true` correction hint that escalates even the first call. Backward-compatible with bare
string / `{model, reasoningEffort}` config.
"""
import json
import unittest
from unittest.mock import MagicMock, patch

from ai_engine.core.gateway import resolve_escalation_effort, resolve_escalation_model
from ai_engine.core.structured import call_with_validation_retry, escalation_requested

AI_MODELS = {
    "report_synthesis": {
        "model": "flash",
        "reasoningEffort": "low",
        "escalation": {"model": "pro", "reasoningEffort": "high"},
    },
    "caption": {"model": "flash"},  # no escalation tier configured
    "transcription": "bare-string-model",
}


class EscalationResolveTests(unittest.TestCase):
    def test_escalation_model_and_effort_when_configured(self):
        self.assertEqual(resolve_escalation_model("report_synthesis", AI_MODELS, fallback_model="flash"), "pro")
        self.assertEqual(resolve_escalation_effort("report_synthesis", AI_MODELS, fallback_effort="low"), "high")

    def test_falls_back_to_base_when_no_escalation(self):
        self.assertEqual(resolve_escalation_model("caption", AI_MODELS, fallback_model="flash"), "flash")
        self.assertIsNone(resolve_escalation_effort("caption", AI_MODELS, fallback_effort=None))
        # A bare string entry (legacy) has no escalation either.
        self.assertEqual(resolve_escalation_model("transcription", AI_MODELS, fallback_model="base"), "base")

    def test_none_ai_models_uses_fallback(self):
        self.assertEqual(resolve_escalation_model("report_synthesis", None, fallback_model="base"), "base")


class EscalationFiringTests(unittest.TestCase):
    def test_validation_retry_fires_escalation_tier(self):
        seen = []

        def invoke(model, effort, correction):
            seen.append((model, effort, correction))
            return "garbage" if correction is None else '{"ok": 1}'

        def parse(raw):
            return json.loads(raw) if raw.startswith("{") else None

        result = call_with_validation_retry(
            task="report_synthesis", ai_models=AI_MODELS, model="flash", effort="low", invoke=invoke, parse=parse,
        )
        self.assertEqual(result, {"ok": 1})
        # First attempt on the base tier; retry escalated to (pro, high).
        self.assertEqual(seen[0][:2], ("flash", "low"))
        self.assertEqual(seen[1][:2], ("pro", "high"))

    def test_escalate_hint_escalates_first_call(self):
        seen = []

        def invoke(model, effort, correction):
            seen.append((model, effort))
            return '{"ok": 1}'

        result = call_with_validation_retry(
            task="report_synthesis", ai_models=AI_MODELS, model="flash", effort="low",
            invoke=invoke, parse=lambda raw: json.loads(raw), escalate=True,
        )
        self.assertEqual(result, {"ok": 1})
        self.assertEqual(len(seen), 1)  # valid first try, no retry
        self.assertEqual(seen[0], ("pro", "high"))  # but the FIRST call already escalated

    def test_escalation_requested_reads_payload_hint(self):
        self.assertTrue(escalation_requested({"escalate": True}))
        self.assertFalse(escalation_requested({"escalate": False}))
        self.assertFalse(escalation_requested({}))
        self.assertFalse(escalation_requested(None))


if __name__ == "__main__":
    unittest.main()
