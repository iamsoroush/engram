"""A note capture's text must reach synthesis even when an API client sends only the file.

The synthesis context reads a note's text from ``metadata.detail`` alone — the uploaded file is a
mirror. A client that posts the file with an empty ``detail`` form field used to produce a capture
whose content hash was the empty string, so the session's synthesis skipped as ``hollow_synthesis``
with no visible error. ``note_detail_with_file_fallback`` closes that hole.
"""

import unittest

from app.services.capture_storage import note_detail_with_file_fallback


class NoteDetailFallbackTest(unittest.TestCase):
    def test_empty_detail_falls_back_to_file_text(self):
        note = "امروز بیست واحد بوتاکس روی پیشانی تزریق کردم."
        self.assertEqual(note_detail_with_file_fallback("", note.encode("utf-8")), note)

    def test_whitespace_detail_falls_back_and_strips(self):
        self.assertEqual(note_detail_with_file_fallback("   ", b"  hello\n"), "hello")

    def test_provided_detail_wins_over_file(self):
        self.assertEqual(note_detail_with_file_fallback("typed text", b"file text"), "typed text")

    def test_undecodable_file_leaves_detail_as_given(self):
        self.assertEqual(note_detail_with_file_fallback("", b"\xff\xfe\x00\x01"), "")


if __name__ == "__main__":
    unittest.main()
