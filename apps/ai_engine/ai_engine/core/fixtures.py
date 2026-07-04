"""Deterministic QA-fixture recognition — the load-bearing gateway-less seam.

The merge-gating real-stack suite (``apps/frontend/tests/e2e-stack/``) drives the whole pipeline
gateway-less by uploading known fixture files; capture jobs (audio/photo/note) and the session job
recognize them via ``is_fixture_capture`` and substitute deterministic text instead of a gateway
call. These constants + this recognizer must survive byte-for-byte in behavior. The heavier
deterministic session builders (mock findings, expected structured report) live with the session job.
"""
from typing import Any

TEST_CAPTURE_TEXT_BY_FILENAME = {
    "audio_01_initial_consultation.wav": "Patient Sara Nazari came for a follow-up after cheek filler. She reports mild asymmetry on the left cheek and wants a conservative correction. No pain, no fever, and no allergy was reported.",
    "photo_01_pre_correction_left_cheek.jpg": "Pre-correction image showing mild left cheek asymmetry before touch-up.",
    "text_note_01.txt": "Patient prefers subtle correction and does not want visible overfilling. Conservative approach requested. Aftercare instructions were given. Patient should send a follow-up photo in 2 weeks if asymmetry persists.",
    "audio_02_procedure_note.wav": "Injected 0.3 mL hyaluronic acid filler into the left mid cheek. Used cannula technique. Patient tolerated the procedure well. Advised no massage and avoid heavy exercise for 24 hours.",
    "photo_02_post_correction_left_cheek.jpg": "Post-correction image showing improved left cheek contour after conservative correction.",
}

TEST_FINAL_SUMMARY = "Follow-up cheek filler correction for mild left cheek asymmetry. Conservative 0.3 mL hyaluronic acid filler touch-up was performed in the left mid cheek using cannula technique. Patient tolerated the procedure well and received aftercare instructions."


def is_fixture_capture(capture: dict[str, Any]) -> bool:
    """Return whether a capture maps to a deterministic QA fixture (skip real enrichment)."""
    metadata = capture.get("metadata") if isinstance(capture.get("metadata"), dict) else {}
    filename = str(metadata.get("original_filename") or "").strip()
    if filename in TEST_CAPTURE_TEXT_BY_FILENAME:
        return True
    detail = " ".join(str(metadata.get("detail") or "").split())
    return "Patient prefers subtle correction" in detail and "follow-up photo in 2 weeks" in detail
