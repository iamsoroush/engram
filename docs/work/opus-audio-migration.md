# Epic: compressed canonical audio (Opus migration)

Process doc (create → build → fold durable essence into `docs/architecture.md` /
`docs/backend/storage.md` / `docs/technical-decisions.md` → delete). Evidence base: the audio-format
sweep in `docs/work/model-compare/readout.md` (Opus 32 kbps 16 kHz mono ≈ 8× smaller than today's
WAV PCM at zero ASR-accuracy cost; Opus 16 kbps REJECTED — drops colloquial doses).

## Goal

Replace the canonical stored audio format WAV PCM 16 kHz mono (~1.92 MB/min) with a compressed
canonical (~0.24 MB/min): ~8× smaller patient-audio uploads (mobile reliability, outbox sync speed),
~8× lower MinIO storage compounding and backup size — and, if verification allows, a smaller
worker→gateway payload by sending the stored compressed bytes directly (today the worker re-encodes
to FLAC per call: `audio_to_flac_mono_16khz_base64` in `jobs/capture_audio.py`).

Standardization itself is non-negotiable: browsers record divergent containers (Chrome webm/opus,
Safari mp4/AAC); exactly ONE canonical format is stored.

## Decision gates (empirical — run them FIRST, in order; each is cheap)

- **G1 — playback.** Native `<audio>` playback of OGG/Opus on real Safari (macOS + iOS) and Chrome,
  including seek + duration + the R6 byte-range path. Historically Safari does not decode
  Ogg/Opus in `<audio>`. If G1 fails → **canonical = MP3 32 kbps 16 kHz mono** (accuracy-equal per
  the sweep, universally decodable) and skip any transcode-on-serve complexity. Do NOT pick a
  format the app cannot play back natively.
- **G2 — direct-to-gateway.** Send the canonical compressed bytes (correct mime, base64) straight
  through the gateway to `gemini-3.1-flash-lite` — the T01–T12 masters transcoded to the canonical
  format, 3 samples each — and compare clinical-token accuracy + CER against the FLAC-path baseline
  from the readout. Gemini's documented list covers OGG *Vorbis*; Opus-in-OGG acceptance is
  unverified. If G2 fails or regresses → keep the worker's FLAC re-encode (it is format-agnostic and
  still works over compressed storage); the storage win stands alone.
- Test material: the WAV masters in the shared infra MinIO, bucket `engram-eval-fixtures`,
  `model-compare/transcription/T01.wav … T12.wav`.

## Stages (after the gates decide the shape)

- **A — backend transcode-on-ingest.** `upload_source_capture` accepts the browser's native
  recorder blob (webm/opus, mp4/AAC — plus WAV for back-compat with existing clients/fixtures);
  normalize ONCE with ffmpeg to the canonical format (16 kHz mono); store ONLY the canonical bytes
  with the correct content-type; measure duration server-side (ffprobe) into capture metadata
  (replaces the client-side duration dance). Replace `validate_wav_pcm_16k_mono` with
  validate-decodable + post-transcode sanity. ffmpeg joins the backend image (dev + prod compose).
- **B — frontend.** Delete the OfflineAudioContext WAV re-encode in
  `features/capture/audio.ts`; upload the MediaRecorder blob as recorded (keeps the 20-min cap;
  saves CPU on old phones). Playback uses the canonical content-type; re-verify the Safari
  duration/range path (R6).
- **C — worker.** If G2 passed: send stored canonical bytes directly (skip the FLAC re-encode),
  keeping the FLAC path behind a config fallback flag. If G2 failed: no worker change.
- **Migration: none.** Existing WAV artifacts stay readable/playable (readers key off the stored
  content-type); only new captures are canonical. Note the mixed-format store in
  `docs/production-alpha-tradeoffs.md`.

## Gates before merge

- Backend unit tests: transcode-on-ingest (each source container), validation, duration, mixed
  WAV/canonical reads. Full backend suite.
- Transcription eval (`EVAL_VOTES=3`) through the changed worker path; must not regress.
- P0 stack e2e (the P0-7 fixture-audio pipeline must pass — its WAV fixture exercises back-compat).
- Manual/visual: record → playback on Chrome (Android) and Safari (iOS) at 390px; audio opens with
  correct duration.
- AI-usage metering unchanged (duration-priced) — assert one metered record.
- Docs close-the-loop: `docs/architecture.md` + `docs/backend/storage.md` audio-format statements,
  a superseding note on the technical-decisions "pending epic" line, then fold + delete this file.
