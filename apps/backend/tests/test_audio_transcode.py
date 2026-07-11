"""Transcode-on-ingest (app/services/audio.py): every capture-audio container normalizes ONCE to the
canonical MP3 16 kHz mono, non-audio is rejected, and duration is measured server-side.

The real-ffmpeg cases are guarded on ffmpeg/ffprobe being present (as the ai-engine media tests guard
their optional deps); CI's ubuntu runners and the backend image both ship ffmpeg. Fixtures are
synthesized at runtime from ffmpeg's lavfi sine source, so no binary blobs are committed.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from app.services import audio

FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
TONE_SECONDS = 1.5


def _encode(container_args: list[str], suffix: str) -> bytes:
    """Synthesize a mono 16 kHz tone and mux it into the requested container via ffmpeg."""
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, f"tone{suffix}")
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={TONE_SECONDS}",
            "-ac", "1", "-ar", "16000", *container_args, out,
        ]
        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode != 0:
            raise unittest.SkipTest(f"ffmpeg lacks an encoder for {suffix}: {proc.stderr.decode()[:200]}")
        with open(out, "rb") as handle:
            return handle.read()


# The source containers a browser (or an older client / e2e fixture) can hand us.
CONTAINERS = {
    "wav (back-compat)": (["-c:a", "pcm_s16le", "-f", "wav"], ".wav"),
    "webm/opus (Chrome)": (["-c:a", "libopus", "-b:a", "32k", "-f", "webm"], ".webm"),
    "mp4/aac (Safari)": (["-c:a", "aac", "-b:a", "64k", "-f", "mp4"], ".m4a"),
    "ogg/opus": (["-c:a", "libopus", "-b:a", "32k", "-f", "ogg"], ".ogg"),
}


@unittest.skipUnless(FFMPEG, "ffmpeg/ffprobe not installed")
class TranscodeOnIngestTest(unittest.TestCase):
    def test_each_container_normalizes_to_canonical_mp3(self):
        for label, (args, suffix) in CONTAINERS.items():
            with self.subTest(container=label):
                source = _encode(args, suffix)
                canonical, duration = audio.normalize_audio_upload(source)
                info = audio.probe_audio(canonical)
                self.assertEqual(info["codec_name"], "mp3")
                self.assertEqual(str(info["sample_rate"]), "16000")
                self.assertEqual(int(info["channels"]), 1)
                self.assertIsNotNone(duration)
                self.assertAlmostEqual(duration, TONE_SECONDS, delta=0.3)

    def test_wav_transcodes_much_smaller_than_source(self):
        # The load-bearing storage win: a WAV PCM 16k upload lands ~8× smaller as canonical MP3.
        wav = _encode(*CONTAINERS["wav (back-compat)"])
        canonical, _ = audio.normalize_audio_upload(wav)
        self.assertLess(len(canonical) * 3, len(wav))  # comfortably >3× smaller (real ratio ~8×)

    def test_canonical_mime_is_mpeg(self):
        self.assertEqual(audio.CANONICAL_AUDIO_MIME, "audio/mpeg")

    def test_probe_reports_duration(self):
        wav = _encode(*CONTAINERS["wav (back-compat)"])
        info = audio.probe_audio(wav)
        self.assertTrue(info["has_audio"])
        self.assertAlmostEqual(info["duration"], TONE_SECONDS, delta=0.2)

    def test_rejects_non_audio(self):
        with self.assertRaises(audio.AudioValidationError):
            audio.normalize_audio_upload(b"this is not audio, it is a text note")

    def test_rejects_empty(self):
        with self.assertRaises(audio.AudioValidationError):
            audio.probe_audio(b"")


class TranscodeToolingGuardTest(unittest.TestCase):
    """ffmpeg-absence surfaces as AudioTranscodeError (a server/env fault), not a validation reject."""

    def test_missing_ffprobe_raises_transcode_error(self):
        with patch("app.services.audio.shutil.which", return_value=None):
            with self.assertRaises(audio.AudioTranscodeError):
                audio.probe_audio(b"\x00\x01")

    def test_missing_ffmpeg_raises_transcode_error(self):
        with patch("app.services.audio.shutil.which", return_value=None):
            with self.assertRaises(audio.AudioTranscodeError):
                audio.transcode_to_canonical(b"\x00\x01")

    def test_startup_assert_names_missing_tools_and_the_fix(self):
        # The boot-time guard (app startup calls this) must crash LOUDLY with the rebuild hint —
        # this is what turns "stuck Waiting to upload after a dev cycle" into a diagnosable boot error.
        with patch("app.services.audio.shutil.which", return_value=None):
            with self.assertRaises(RuntimeError) as ctx:
                audio.assert_audio_tooling()
        message = str(ctx.exception)
        self.assertIn("ffmpeg", message)
        self.assertIn("ffprobe", message)
        self.assertIn("rebuild", message)

    def test_startup_assert_passes_when_tooling_present(self):
        audio.assert_audio_tooling()  # the test image installs ffmpeg; must not raise

    def test_upload_maps_transcode_error_to_503(self):
        # A server-side transcode fault is an honest 503 (outbox keeps retrying; operator sees why),
        # never a bare 500 and never a 400 blaming the client's audio.
        import asyncio
        from unittest.mock import MagicMock
        from fastapi import HTTPException
        from app.services import capture_storage

        upload = MagicMock()
        upload.read = unittest.mock.AsyncMock(return_value=b"RIFF-fake-audio")
        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = None  # no client_capture_id dedup hit
        with patch.object(capture_storage, "normalize_audio_upload", side_effect=audio.AudioTranscodeError("ffprobe is not installed")):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(
                    capture_storage.upload_source_capture(
                        db,
                        object_store=MagicMock(),
                        principal=MagicMock(tenant_id=None, user_id=None),
                        capture_type_text="audio",
                        session_id=None,
                        patient_id=None,
                        client_capture_id="t-503",
                        detail="",
                        file=upload,
                    )
                )
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("ffprobe", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
