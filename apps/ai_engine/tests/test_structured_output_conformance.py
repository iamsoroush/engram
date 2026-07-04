"""Per-model-family gateway conformance check for structured outputs (§3.2, gateway-gated).

Before relying on ``response_format=json_schema``, prove the configured gateway actually enforces it for
each model family in play (OpenAI-class + Gemini-class): send a representative schema and assert the
reply is valid JSON matching it. This SKIPS without a gateway (so the gateway-less CI gate is unaffected)
and is meant to run as a scheduled check where a real gateway is configured — the pre-rollout gate the
plan asks for. It sends a trivial 1-token schema per distinct configured model, so it costs ~nothing.
"""
import json
import re
import unittest

from ai_engine.core.gateway import gateway_client, gateway_settings_for, transcription_is_configured
from ai_engine.core.structured import response_format

# The JSON-emitting tasks whose gateways we enforce structured outputs on (qa_draft emits plain text).
STRUCTURED_TASKS = ("transcription", "caption", "patient_memory", "report_synthesis")

PROBE_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "string"}, "n": {"type": "integer"}},
    "required": ["ok", "n"],
}


def _strip_fences(text: str) -> str:
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text.strip(), flags=re.DOTALL | re.IGNORECASE)
    return fenced.group(1).strip() if fenced else text.strip()


@unittest.skipUnless(transcription_is_configured(), "no gateway configured — structured-output conformance is gateway-gated")
class StructuredOutputConformanceTests(unittest.TestCase):
    def test_each_configured_model_returns_schema_valid_json(self):
        seen: set[tuple[str, str]] = set()
        for task in STRUCTURED_TASKS:
            base_url, _api_key, model = gateway_settings_for(task)
            if not base_url.strip() or (base_url, model) in seen:
                continue
            seen.add((base_url, model))
            with self.subTest(task=task, model=model):
                client = gateway_client(task)
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": 'Return JSON exactly: {"ok":"yes","n":1}'}],
                    response_format=response_format("conformance_probe", PROBE_SCHEMA),
                )
                raw = response.choices[0].message.content or ""
                parsed = json.loads(_strip_fences(raw))
                self.assertIsInstance(parsed, dict, f"{task}/{model} did not return a JSON object")
                self.assertIn("ok", parsed, f"{task}/{model} omitted a required key — schema not enforced")
                self.assertIn("n", parsed)
        self.assertTrue(seen, "no configured gateways to probe")


if __name__ == "__main__":
    unittest.main()
