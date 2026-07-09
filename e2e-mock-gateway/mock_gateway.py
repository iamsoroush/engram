"""Deterministic OpenAI-compatible mock gateway for the e2e-stack-ai (P1) suite.

The AI engine talks to an OpenAI-compatible gateway (``{base_url}/chat/completions``). In P1 we point
it here instead of a real LLM, so synthesis / patient-memory / Q&A jobs resolve deterministically with
zero keys. Responses are routed by the request's ``response_format`` name and message content, and the
canned payloads are derived from the AI-engine unit fixtures
(``apps/ai_engine/tests/test_report_synthesis.py`` etc.) so schema drift breaks the P1 job loudly.

No third-party deps — runs on ``python:3.13-slim`` with only the stdlib. See docker-compose.e2e-ai.yml.
"""

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 9099
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def _capture_ids(prompt: str) -> list[str]:
    """Best-effort: the synthesis prompt embeds the session's capture UUIDs; reuse them so the
    synthesized treatments/media reference real captures."""
    seen: list[str] = []
    for cid in UUID_RE.findall(prompt or ""):
        if cid not in seen:
            seen.append(cid)
    return seen


def _synthesis(prompt: str) -> str:
    ids = _capture_ids(prompt)
    first = ids[0] if ids else "cap-a"
    blocks_media = [{"type": "image", "captureId": cid, "caption": "Left cheek"} for cid in ids[:1]]
    payload = {
        "summary": "Follow-up cheek-filler touch-up on the left cheek.",
        "language": "en",
        "sections": [
            {"id": "visit-summary", "title": "Visit summary",
             "blocks": [{"type": "paragraph", "text": "Patient returned for a conservative left-cheek correction."}]},
            {"id": "treatment-performed", "title": "Treatment performed",
             "blocks": [{"type": "paragraph", "text": "0.3 mL hyaluronic acid filler to the left mid cheek."}]},
            {"id": "media", "title": "Media", "blocks": blocks_media},
        ],
        # A fully-specified treatment so the Pro report renders a structured row (brand + dose + lot).
        "treatments": [{
            "area": "left cheek", "product": "hyaluronic acid filler", "brand": "Juvederm",
            "quantity": 0.3, "unit": "mL", "quantityText": "0.3 mL", "lot": "D-4471",
            "confidence": 0.92, "status": "performed", "sourceCaptureIds": ids or [first], "evidence": "spoken",
            "carriedForward": False, "supersedesCaptureId": None, "attributes": {"needleGauge": "27G"},
        }],
        "uncertainties": [],
        "aftercareSelections": [],
        # A safety flag so the report surfaces + the rejection flow can be exercised.
        "safetyFlags": [{"kind": "allergy", "text": "Patient reported a lidocaine sensitivity.", "sourceCaptureIds": ids}],
    }
    return json.dumps(payload, ensure_ascii=False)


def _transcription() -> str:
    return json.dumps({
        "transcript": "Patient returned for a left-cheek filler touch-up; conservative correction requested.",
        "language": "en",
        "patient_information": {"standardized_display_name": None, "raw_mentioned_name": None,
                                "national_id": None, "confidence": 0.0, "evidence": None},
        "clinical_summary": "Left-cheek filler follow-up.",
        "uncertainties": [],
        "intents": None,
    }, ensure_ascii=False)


def _caption() -> str:
    return json.dumps({
        "caption": "Left cheek before the touch-up.",
        "display": "Left cheek before the touch-up.",
        "confidence": 0.9,
        "outOfContext": {"present": False, "reason": None, "confidence": 0.0},
        "pairing": None,
        "uncertainties": [],
    }, ensure_ascii=False)


def _patient_memory() -> str:
    return json.dumps({
        "summary": "Returning aesthetics patient, conservative left-cheek filler follow-ups.",
        "history": {
            "snapshot": "Left-cheek filler patient, prefers subtle correction.",
            "sections": [{"label": "Story so far", "body": "Conservative left-cheek filler touch-ups."}],
            "visits": [],
        },
        "card": {"storySoFar": "Conservative left-cheek filler.", "rightNow": "Follow-up touch-up done.", "flags": []},
    }, ensure_ascii=False)


def _route(body: dict) -> str:
    """Return the assistant message content for a chat.completions request."""
    fmt = (body.get("response_format") or {}).get("json_schema") or {}
    name = fmt.get("name", "")
    messages = body.get("messages") or []
    prompt_text = ""
    has_audio = has_image = False
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            prompt_text += content
        elif isinstance(content, list):
            for part in content:
                ptype = part.get("type")
                if ptype == "input_audio":
                    has_audio = True
                elif ptype == "image_url":
                    has_image = True
                elif ptype == "text":
                    prompt_text += part.get("text", "")

    if name == "session_synthesis_output":
        return _synthesis(prompt_text)
    if name == "safety_reconcile_output":
        return json.dumps({"decisions": []})  # no cross-visit reconcile changes
    if has_audio:
        return _transcription()
    if has_image:
        return _caption()
    if "snapshot" in prompt_text or "storySoFar" in prompt_text:
        return _patient_memory()
    # Q&A draft (plain text).
    return "Hi — thanks for reaching out. Based on your recent visit, this is usually normal; rest and reach out if it worsens. — Your care team"


def _completion(content: str, model: str) -> dict:
    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": 0,
        "model": model or "mock",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop", "logprobs": None}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: dict) -> None:
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/health":
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            body = {}
        model = body.get("model", "mock")
        if self.path.endswith("/audio/transcriptions"):
            self._send(200, {"text": json.loads(_transcription())["transcript"]})
            return
        # Everything else is treated as a chat.completions call.
        self._send(200, _completion(_route(body), model))

    def log_message(self, *args) -> None:  # quiet
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
