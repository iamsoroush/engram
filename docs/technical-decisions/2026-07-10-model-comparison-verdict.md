# Model comparison verdict: keep the incumbent split; mid bracket rejected (2026-07-10)

A 74-case owner-designed comparison (all text AI jobs + transcription + audio formats; verdict + evidence recorded here; the reusable
case files + transcription scripts remain in `apps/ai_engine/eval/model_compare/`) validated the current production config as the champion:
`gpt-5.4-nano` for synthesis + safety-reconcile (blind judge 30–4 on synthesis, cheaper than the
Gemini peer), `gemini-3.1-flash-lite` for qa_draft / patient-memory / transcription (the OpenAI
models leak a cross-patient dose on Q&A 3/3; Gemini doesn't — the split exploits opposite safety
personalities). The mid bracket (`gpt-5.4-mini`, subbed for the unavailable `gpt-5.6-luna`) buys
~equal quality at ~3.5× token cost — halving usage-limit headroom (823 → 459 effective visits per
$10/seat) — and `gemini-3.5-flash` is disqualified operationally (46–56% HTTP-503 under load,
40–100 s latency, ~9× nano cost). Revisit only when a provider ships a new price-class or the
gateway gains `gpt-5.6` access. Fallout fixed alongside: `services/ai_usage/pricing.py` rates
refreshed to live 2026-07-10 pricing (the meter was under-pricing Gemini jobs 2.5–3.75×), and the
systemic C34 name-leak got a synthesis v17 prompt guard + a permanent eval case.
The audio-format add-on's verdict: canonical stored format should move WAV PCM → **OGG/Opus
32 kbps 16 kHz mono** (~8× smaller uploads + MinIO storage, zero accuracy cost; Opus 16 kbps
rejected — it drops colloquial doses), implemented server-side as transcode-on-ingest; the gateway
path is unaffected because the worker already re-encodes to FLAC per call. Implementation is a
pending epic — not yet built.
**Superseded 2026-07-10 (built): canonical = MP3 32 kbps (not Opus), and the worker sends it
directly (drops the FLAC re-encode). See [Compressed canonical audio](2026-07-10-compressed-canonical-audio.md).**
