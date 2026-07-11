"""R6 — the capture media endpoint must serve source bytes with HTTP byte-range support.

Safari needs ``Accept-Ranges: bytes`` (and a ``206`` for a Range request) to compute a WAV's duration;
without it the player shows 0:00. The ``/captures/{id}/file-content`` route delegates to the shared
``ranged_file_response`` helper — this test guards that the route actually wires range handling through
(full-body 200 carries Accept-Ranges; a Range header yields 206 Partial Content).
"""

import unittest
from unittest.mock import MagicMock, patch

from app import captures_api

WAV = b"RIFF----WAVEfmt " + bytes(range(64))  # stand-in source bytes


class CaptureFileContentRangeTest(unittest.TestCase):
    def _call(self, range_header=None, *, content=WAV, media_type="audio/wav", filename="note.wav"):
        served = {"content": content, "media_type": media_type, "filename": filename}
        with patch.object(captures_api, "source_file_content", return_value=served):
            return captures_api.get_capture_file_content(
                capture_id="cap-1",
                range_header=range_header,
                principal=MagicMock(),
                db=MagicMock(),
                object_store=MagicMock(),
            )

    def test_full_body_advertises_range_support(self):
        resp = self._call()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["Accept-Ranges"], "bytes")
        self.assertEqual(resp.headers["Content-Length"], str(len(WAV)))
        self.assertEqual(resp.media_type, "audio/wav")

    def test_range_request_returns_206_partial(self):
        resp = self._call(range_header="bytes=0-15")
        self.assertEqual(resp.status_code, 206)
        self.assertEqual(resp.headers["Accept-Ranges"], "bytes")
        self.assertEqual(resp.body, WAV[:16])
        self.assertEqual(resp.headers["Content-Range"], f"bytes 0-15/{len(WAV)}")

    def test_canonical_mp3_served_with_stored_mime_and_range(self):
        # Post-migration, new captures are canonical MP3; the serve path is format-agnostic — it keys
        # off the artifact's stored mime, so a mixed store (old WAV + new MP3) both serve correctly.
        mp3 = b"ID3" + bytes(range(64))
        full = self._call(content=mp3, media_type="audio/mpeg", filename="audio-1.mp3")
        self.assertEqual(full.status_code, 200)
        self.assertEqual(full.media_type, "audio/mpeg")
        self.assertEqual(full.headers["Accept-Ranges"], "bytes")
        part = self._call(range_header="bytes=0-9", content=mp3, media_type="audio/mpeg", filename="audio-1.mp3")
        self.assertEqual(part.status_code, 206)
        self.assertEqual(part.body, mp3[:10])


if __name__ == "__main__":
    unittest.main()
