"""Cache-stability acceptance tests for the stable-prefix synthesis context layout (G2–G4).

The synthesis prompt is re-run minutes apart inside the gateway's prefix-cache TTL; the ~10x
cached-input discount only lands when run N+1's serialized context byte-EXTENDS run N's. These tests
pin the two properties that guarantee it:

  1. Building the SAME context twice serializes byte-identically (no run-to-run nondeterminism).
  2. Appending ONE capture leaves the whole stable region (instructions/clinic/patient blocks) and the
     already-present captures byte-identical — only the appended capture + the volatile tail differ.

They are DB-free (repo convention): they exercise `serialize_synthesis_context`, the byte-authoritative
serializer both the backend and the ai_engine synthesis prompt order against. The real-DB build path is
covered by the e2e-stack + hermetic suites.
"""
import os
import unittest

from app.services.session_processing import (
    SYNTHESIS_STABLE_KEYS,
    SYNTHESIS_VOLATILE_KEYS,
    ordered_synthesis_context,
    serialize_synthesis_context,
)

CAPTURES_MARKER = '"captures":'


def _capture(capture_id: str, captured_at: str, *, transcript: str | None = None) -> dict:
    return {
        "captureId": capture_id,
        "type": "audio",
        "status": "processed",
        "capturedAt": captured_at,
        "transcript": transcript or f"note {capture_id}",
    }


def _context(captures: list[dict], *, changeset=None, prior_report=None) -> dict:
    """A representative synthesis context in the shape the backend builder emits."""
    return {
        "schemaVersion": "2026-05-21.session-processing-input.v1",
        "domain": {"label": "aesthetics clinic", "areaCodes": ["cheeks", "forehead"]},
        "clinic": {"name": "Demo Clinic", "information": ["Clinical memory report"]},
        "reportLanguage": "fa",
        "aftercareTemplates": [
            {"id": "t1", "name": "Botox", "procedureType": "botox", "body": "..."},
            {"id": "t2", "name": "Filler", "procedureType": "filler", "body": "..."},
        ],
        "assignedPatient": {"patientId": "p1", "displayName": "زهرا"},
        "patientSummarizedHistory": "prior visits summary",
        "patientSafetyFlags": [{"key": "allergy|x", "kind": "allergy", "text": "x"}],
        "referencePriorVisitTreatments": [{"treatmentKey": "cheeks|ژل", "product": "ژل"}],
        "session": {"id": "s1", "title": "Follow-up"},
        "rawReportTemplate": {"patient_information": "{{ patient_information }}", "body": "{{ body }}"},
        "captures": captures,
        "changeset": changeset if changeset is not None else {"addedCaptureIds": [], "removedCaptureIds": []},
        "priorDraftTreatments": [],
        "priorReportModel": prior_report or {"sections": [], "summary": "prior"},
    }


class SerializationDeterminismTests(unittest.TestCase):
    def test_byte_identical_when_built_twice(self):
        captures = [_capture("c1", "2026-07-01T10:00:00"), _capture("c2", "2026-07-01T10:05:00")]
        self.assertEqual(serialize_synthesis_context(_context(captures)), serialize_synthesis_context(_context(captures)))

    def test_raw_report_template_is_excluded_from_the_llm_context(self):
        serialized = serialize_synthesis_context(_context([_capture("c1", "2026-07-01T10:00:00")]))
        self.assertNotIn("rawReportTemplate", serialized)

    def test_captures_precede_every_volatile_key(self):
        serialized = serialize_synthesis_context(_context([_capture("c1", "2026-07-01T10:00:00")]))
        captures_at = serialized.index(CAPTURES_MARKER)
        for volatile_key in SYNTHESIS_VOLATILE_KEYS:
            marker = f'"{volatile_key}":'
            if marker in serialized:
                self.assertLess(captures_at, serialized.index(marker), f"{volatile_key} must serialize AFTER captures")

    def test_stable_keys_precede_captures_in_order(self):
        serialized = serialize_synthesis_context(_context([_capture("c1", "2026-07-01T10:00:00")]))
        captures_at = serialized.index(CAPTURES_MARKER)
        positions = [serialized.index(f'"{key}":') for key in SYNTHESIS_STABLE_KEYS if f'"{key}":' in serialized]
        self.assertEqual(positions, sorted(positions), "stable keys must serialize in their declared order")
        self.assertTrue(all(pos < captures_at for pos in positions), "all stable keys precede captures")


class PrefixExtensionTests(unittest.TestCase):
    def _stable_region(self, serialized: str) -> str:
        return serialized.split(CAPTURES_MARKER, 1)[0]

    def test_stable_region_unchanged_when_a_capture_is_appended(self):
        before = [_capture("c1", "2026-07-01T10:00:00"), _capture("c2", "2026-07-01T10:05:00")]
        after = before + [_capture("c3", "2026-07-01T10:10:00")]  # append-only, chronological
        s_before = serialize_synthesis_context(_context(before))
        s_after = serialize_synthesis_context(_context(after))
        self.assertEqual(self._stable_region(s_before), self._stable_region(s_after))

    def test_serialized_common_prefix_extends_through_the_prior_captures(self):
        before = [_capture("c1", "2026-07-01T10:00:00"), _capture("c2", "2026-07-01T10:05:00")]
        after = before + [_capture("c3", "2026-07-01T10:10:00")]
        s_before = serialize_synthesis_context(_context(before))
        s_after = serialize_synthesis_context(_context(after))
        common = os.path.commonprefix([s_before, s_after])
        # The shared prefix must reach past the stable region AND into the already-present captures — the
        # cache win. c1 and c2's ids must live inside the common (cached) prefix; c3 is the divergence.
        self.assertGreater(len(common), len(self._stable_region(s_before)))
        self.assertIn('"c1"', common)
        self.assertIn('"c2"', common)

    def test_volatile_only_change_leaves_the_stable_region_identical(self):
        captures = [_capture("c1", "2026-07-01T10:00:00")]
        s_a = serialize_synthesis_context(_context(captures, changeset={"addedCaptureIds": ["c1"], "removedCaptureIds": []}, prior_report={"sections": [], "summary": "A"}))
        s_b = serialize_synthesis_context(_context(captures, changeset={"addedCaptureIds": ["x"], "removedCaptureIds": ["y"]}, prior_report={"sections": [], "summary": "B — totally different"}))
        self.assertEqual(self._stable_region(s_a), self._stable_region(s_b))

    def test_grouped_captures_dict_does_NOT_byte_extend_on_append(self):
        # Guard proving the test has teeth: the OLD grouped {audio,photos,text} shape splices a new photo
        # into the middle group, so the captures region does NOT byte-extend — which is exactly why G3
        # flattens captures to one chronological list. (Documents the regression the flat list prevents.)
        grouped_before = {"audio": [_capture("c1", "t1")], "photos": [], "text": []}
        grouped_after = {"audio": [_capture("c1", "t1")], "photos": [_capture("c2", "t2")], "text": []}
        ctx_before = {**_context([]), "captures": grouped_before}
        ctx_after = {**_context([]), "captures": grouped_after}
        s_before = serialize_synthesis_context(ctx_before)
        s_after = serialize_synthesis_context(ctx_after)
        # Stable region still holds (the serializer orders it), but the captures no longer byte-extend:
        self.assertEqual(s_before.split(CAPTURES_MARKER)[0], s_after.split(CAPTURES_MARKER)[0])
        common = os.path.commonprefix([s_before, s_after])
        self.assertNotIn('"c2"', common)  # the appended photo is NOT in the cached prefix — the loss


class OrderedContextStructureTests(unittest.TestCase):
    def test_leftover_unknown_keys_append_to_the_tail(self):
        ctx = {**_context([_capture("c1", "t1")]), "someFutureField": {"z": 1}}
        ordered = list(ordered_synthesis_context(ctx).keys())
        self.assertEqual(ordered[-1], "someFutureField")
        self.assertLess(ordered.index("captures"), ordered.index("someFutureField"))


if __name__ == "__main__":
    unittest.main()
