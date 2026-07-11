"""Server-side audio normalization — transcode-on-ingest to the single canonical stored format.

Browsers record divergent containers (Chrome ``webm/opus``, Safari ``mp4/AAC``); older clients and the
e2e fixtures send WAV. This module normalizes every capture-audio upload ONCE to the canonical stored
format — **MP3 32 kbps, 16 kHz mono** — so the object store holds exactly one format at ~8× smaller
than the old WAV-PCM-16k store (~1.92 MB/min → ~0.24 MB/min), at zero transcription-accuracy cost
(the audio-format sweep; see ``docs/technical-decisions.md`` and ``docs/backend/storage.md``).
``ffmpeg``/``ffprobe`` are shelled out to; the backend image installs them.

Canonical = MP3, per decision gate **G1**: MP3 plays natively in ``<audio>`` with exact duration +
seek on Chrome and Safari (incl. iOS) through our byte-range path, and is universally decodable;
Ogg/Opus playback + duration is unreliable on iOS (and overshot duration even on macOS Safari).
Flipping the canonical to Opus later is a one-place change here (``CANONICAL_*`` +
``_CANONICAL_FFMPEG_OUTPUT_ARGS``) — gated on an iOS-Safari playback re-test.
"""
import json
import os
import shutil
import subprocess
import tempfile


def assert_audio_tooling() -> None:
    """Fail FAST when ffmpeg/ffprobe are missing — called at app startup.

    The binaries live in the backend IMAGE, but dev stacks bind-mount code over an existing
    container: after a dependency-adding change, the code updates while the image does not, and the
    first audio upload dies with an opaque 500 the outbox retries forever ("Waiting to upload").
    Crashing at boot with the fix in the message turns that silent drift into a loud, diagnosable
    startup error.
    """
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        raise RuntimeError(
            f"Audio tooling missing from this container: {', '.join(missing)}. The backend image is "
            "stale — rebuild it (scripts/dev-stack.sh up, or: docker compose build backend)."
        )


# --- canonical format: the single source of truth ---------------------------------------------
CANONICAL_AUDIO_MIME = "audio/mpeg"
CANONICAL_AUDIO_EXTENSION = "mp3"
# ffmpeg output args producing the canonical format: mono, 16 kHz, MP3 CBR 32 kbps.
_CANONICAL_FFMPEG_OUTPUT_ARGS = [
    "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "32k", "-f", "mp3",
]


class AudioValidationError(ValueError):
    """Uploaded bytes are not decodable audio — the upload must be rejected (HTTP 400)."""


class AudioTranscodeError(RuntimeError):
    """A server-side problem (ffmpeg missing, or decodable audio failed to transcode)."""


def probe_audio(content: bytes) -> dict[str, object]:
    """ffprobe raw bytes; return ``{duration, codec_name, sample_rate, channels, has_audio}``.

    Raises ``AudioValidationError`` when the bytes are not a decodable audio stream (this is the
    "validate-decodable" replacement for the old strict WAV-PCM header check), and
    ``AudioTranscodeError`` when ffprobe itself is unavailable.
    """
    if shutil.which("ffprobe") is None:
        raise AudioTranscodeError("ffprobe is not installed or not on PATH")
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "probe.bin")
        with open(src, "wb") as handle:
            handle.write(content)
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration:stream=codec_type,codec_name,sample_rate,channels",
                "-of", "json", src,
            ],
            capture_output=True,
        )
    if proc.returncode != 0:
        raise AudioValidationError("Uploaded file is not decodable audio")
    try:
        info = json.loads(proc.stdout.decode("utf-8", "replace") or "{}")
    except json.JSONDecodeError as exc:
        raise AudioValidationError("Uploaded file is not decodable audio") from exc
    audio_streams = [s for s in (info.get("streams") or []) if s.get("codec_type") == "audio"]
    if not audio_streams:
        raise AudioValidationError("Uploaded file has no audio stream")
    stream = audio_streams[0]
    fmt = info.get("format") or {}
    duration: float | None = None
    for candidate in (fmt.get("duration"), stream.get("duration")):
        try:
            if candidate is not None:
                duration = float(candidate)
                break
        except (TypeError, ValueError):
            continue
    return {
        "duration": duration,
        "codec_name": stream.get("codec_name"),
        "sample_rate": stream.get("sample_rate"),
        "channels": stream.get("channels"),
        "has_audio": True,
    }


def transcode_to_canonical(content: bytes) -> bytes:
    """Transcode arbitrary decodable audio to the canonical MP3 32 kbps 16 kHz mono bytes."""
    if shutil.which("ffmpeg") is None:
        raise AudioTranscodeError("ffmpeg is not installed or not on PATH")
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in")
        dst = os.path.join(tmp, f"out.{CANONICAL_AUDIO_EXTENSION}")
        with open(src, "wb") as handle:
            handle.write(content)
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src, *_CANONICAL_FFMPEG_OUTPUT_ARGS, dst],
            capture_output=True,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", "replace").strip()
            raise AudioTranscodeError(f"Audio transcode to {CANONICAL_AUDIO_EXTENSION} failed: {stderr or proc.returncode}")
        with open(dst, "rb") as handle:
            return handle.read()


def normalize_audio_upload(content: bytes) -> tuple[bytes, float | None]:
    """Validate → transcode → measure. Return ``(canonical_bytes, duration_seconds)``.

    Duration is read from the CANONICAL output (exactly what we store and what the worker later
    ffprobes for per-minute billing), so the UI duration and the meter agree. Raises
    ``AudioValidationError`` for non-audio input (→ HTTP 400 at the call site); ``AudioTranscodeError``
    for a server-side ffmpeg problem (→ retryable 500, capture stays durable in the client outbox).
    """
    probe_audio(content)  # validate decodable audio before spending a transcode
    canonical = transcode_to_canonical(content)
    duration = probe_audio(canonical)["duration"]
    return canonical, duration if isinstance(duration, float) else None
