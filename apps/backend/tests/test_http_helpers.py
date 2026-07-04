"""Unit tests for the extracted HTTP plumbing (byte-range responses + metadata form parsing).

These pure helpers used to live inline in ``main.py`` with no direct coverage; the byte-range
branch logic (206/416/full-body) is the interesting part and is exercised here.
"""

import unittest

from fastapi import HTTPException

from app.http.forms import parse_metadata_form
from app.http.responses import ranged_file_response

BODY = b"0123456789"  # 10 bytes


class RangedFileResponseTest(unittest.TestCase):
    def test_no_range_returns_full_body(self) -> None:
        resp = ranged_file_response(BODY, "audio/mpeg", "clip.mp3")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.body, BODY)
        self.assertEqual(resp.headers["Content-Length"], "10")
        self.assertEqual(resp.headers["Accept-Ranges"], "bytes")
        self.assertIn('filename="clip.mp3"', resp.headers["Content-Disposition"])
        self.assertNotIn("Content-Range", resp.headers)

    def test_valid_range_returns_partial(self) -> None:
        resp = ranged_file_response(BODY, "audio/mpeg", "clip.mp3", range_header="bytes=2-5")
        self.assertEqual(resp.status_code, 206)
        self.assertEqual(resp.body, b"2345")
        self.assertEqual(resp.headers["Content-Length"], "4")
        self.assertEqual(resp.headers["Content-Range"], "bytes 2-5/10")

    def test_open_ended_range_runs_to_end(self) -> None:
        resp = ranged_file_response(BODY, "audio/mpeg", "clip.mp3", range_header="bytes=7-")
        self.assertEqual(resp.status_code, 206)
        self.assertEqual(resp.body, b"789")
        self.assertEqual(resp.headers["Content-Range"], "bytes 7-9/10")

    def test_end_past_eof_is_clamped(self) -> None:
        resp = ranged_file_response(BODY, "audio/mpeg", "clip.mp3", range_header="bytes=8-99")
        self.assertEqual(resp.status_code, 206)
        self.assertEqual(resp.body, b"89")
        self.assertEqual(resp.headers["Content-Range"], "bytes 8-9/10")

    def test_start_at_or_past_eof_is_416(self) -> None:
        resp = ranged_file_response(BODY, "audio/mpeg", "clip.mp3", range_header="bytes=10-12")
        self.assertEqual(resp.status_code, 416)
        self.assertEqual(resp.headers["Content-Range"], "bytes */10")

    def test_non_bytes_unit_is_416(self) -> None:
        resp = ranged_file_response(BODY, "audio/mpeg", "clip.mp3", range_header="items=0-1")
        self.assertEqual(resp.status_code, 416)

    def test_missing_start_is_416(self) -> None:
        resp = ranged_file_response(BODY, "audio/mpeg", "clip.mp3", range_header="bytes=-3")
        self.assertEqual(resp.status_code, 416)

    def test_non_numeric_range_is_416(self) -> None:
        resp = ranged_file_response(BODY, "audio/mpeg", "clip.mp3", range_header="bytes=a-b")
        self.assertEqual(resp.status_code, 416)


class ParseMetadataFormTest(unittest.TestCase):
    def test_empty_or_none_returns_none(self) -> None:
        self.assertIsNone(parse_metadata_form(None))
        self.assertIsNone(parse_metadata_form(""))

    def test_valid_object_is_parsed(self) -> None:
        self.assertEqual(parse_metadata_form('{"a": 1, "b": "x"}'), {"a": 1, "b": "x"})

    def test_invalid_json_raises_400(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            parse_metadata_form("{not json")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_non_object_json_raises_400(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            parse_metadata_form("[1, 2, 3]")
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
