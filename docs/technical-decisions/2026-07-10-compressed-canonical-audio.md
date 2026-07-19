# Compressed canonical audio: MP3 canonical + direct-to-gateway (2026-07-10)

The compressed-canonical-audio epic shipped the ~8× storage/upload win. Two empirical gates set the
shape:

- **G1 (playback) → canonical is MP3 32 kbps 16 kHz mono, not OGG/Opus.** On real Chrome and macOS
  Safari 26.3, MP3 plays natively in `<audio>` with exact duration + working seek through our
  byte-range path; Ogg/Opus overshot duration by ~1 s even where it played on macOS Safari, and its
  iOS `<audio>` support is historically unreliable (not verifiable here). MP3 is universally
  decodable and the size penalty vs Opus 32 kbps is ~4% (7.9× vs 8.1×) — negligible. The stored
  format is a single constant in `app/services/audio.py`; flipping to Opus later is a one-line change
  gated on an iOS-Safari playback re-test.
- **G2 (direct-to-gateway) → PASS.** The gateway (`gemini-3.1-flash-lite`) accepts the canonical MP3
  bytes directly (`audio/mp3`); over the T01–T12 owner clips (3 samples) direct-send matched the
  FLAC-path baseline on CER (0.075) and clinical-token accuracy with zero errors, and a
  stored-MP3→direct vs stored-MP3→FLAC control was identical (re-encoding lossy MP3 to FLAC recovers
  nothing). So the worker sends stored bytes directly; the FLAC re-encode is retained behind
  `AI_ENGINE_TRANSCRIPTION_DIRECT_SEND` for legacy WAV / unknown formats and as a kill-switch.

Built: backend transcode-on-ingest with server-side ffprobe duration (`app/services/audio.py`,
ffmpeg added to the backend image); frontend drops the OfflineAudioContext WAV re-encode and uploads
the native recorder blob; worker direct-send. No bulk migration — the store is mixed (old WAV + new
MP3), readers key off `artifact.mime_type`. Metering stays duration-priced: the worker's duration
probe was made robust (temp-file ffprobe) so per-minute billing works for MP3, not just WAV.
