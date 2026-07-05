"""E3 — cross-visit projection / share / lifecycle invariants (correctness-register Track E3).

Pure-logic unit tests (no DB) for the projection-side fixes: memory staleness/snapshot invariants
(M-P1/M-P2/M-P5/M-P9/M-P12), the share lot-filter + overlay reads (Q-6/M-P4), and share-staleness
(Q-4). DB-wired behaviour (reassignment revocation, archive hooks) is covered by the assignment /
capture-undo suites.
"""
import unittest
import uuid
from datetime import datetime, timezone

from app.models import Patient, Session
from app.services.patient_memory_intelligence import (
    apply_patient_memory_output,
    build_patient_memory_job_input,
    memory_build_snapshot,
    memory_matches_tier,
    memory_updated_at,
    patient_memory_is_stale,
)
from app.services.patient_surface import (
    SHARE_STATUS_ACTIVE,
    SHARE_STATUS_REVOKED,
    _curated_treatment_lines,
    _share_is_stale,
    _strip_lot_tokens,
)


def _session(sid=None, *, updated_at=None, treatments=None, overlay=None):
    s = Session()
    s.id = sid or uuid.uuid4()
    when = updated_at or datetime(2026, 6, 7, tzinfo=timezone.utc)
    s.captured_at = when
    s.created_at = when
    s.updated_at = when
    meta = {"capture_count": 1, "latest_capture_type": "audio"}
    if treatments is not None:
        meta["treatments"] = treatments
    if overlay is not None:
        meta["treatment_overlay"] = overlay
    s.extracted_metadata = meta
    return s


def _patient(name="Sara Nazari", memory=None):
    p = Patient()
    p.id = uuid.uuid4()
    p.display_name = name
    p.memory = memory
    return p


class MemoryStalenessTests(unittest.TestCase):
    def test_no_memory_is_stale(self):
        self.assertTrue(patient_memory_is_stale(_patient(), [_session()]))

    def test_no_sessions_never_stale(self):
        self.assertFalse(patient_memory_is_stale(_patient(), []))

    def test_reassignment_removed_session_is_stale(self):
        # M-P2: the built-from session set no longer matches the current set → stale (a reassignment
        # removed a visit whose remaining timestamps never move).
        s1, s2 = _session(), _session()
        patient = _patient(memory={
            "status": "ready", "mode": "pro", "summary": "x",
            "updated_at": "2026-06-08T00:00:00+00:00",
            "built_from_sessions": sorted([str(s1.id), str(s2.id)]),
            "built_from_name": "Sara Nazari",
        })
        # Both sessions present → not stale.
        self.assertFalse(patient_memory_is_stale(patient, [s1, s2]))
        # s2 reassigned away → only s1 remains → set differs → stale.
        self.assertTrue(patient_memory_is_stale(patient, [s1]))

    def test_rename_is_stale(self):
        # M-P9: a rename since the build → stale (built_from_name differs).
        s1 = _session()
        patient = _patient(name="New Name", memory={
            "status": "ready", "mode": "pro", "summary": "x",
            "updated_at": "2026-06-08T00:00:00+00:00",
            "built_from_sessions": [str(s1.id)],
            "built_from_name": "Old Name",
        })
        self.assertTrue(patient_memory_is_stale(patient, [s1]))


class MemorySnapshotTests(unittest.TestCase):
    def test_apply_stamps_from_snapshot_not_completion(self):
        # M-P5: freshness is the build-START snapshot time, not completion time.
        patient = _patient()
        s1 = _session()
        snapshot = memory_build_snapshot(patient, [s1], now=datetime(2026, 6, 9, tzinfo=timezone.utc))
        apply_patient_memory_output(
            patient,
            {"summary": "AI story", "history": {"snapshot": "s", "sections": [{"label": "a", "body": "b"}]}, "source": "ai:x"},
            "pro",
            now=datetime(2026, 6, 30, tzinfo=timezone.utc),  # much later completion
            snapshot=snapshot,
        )
        self.assertEqual(memory_updated_at(patient), snapshot["updated_at"])
        self.assertEqual(patient.memory["built_from_sessions"], [str(s1.id)])
        self.assertEqual(patient.memory["built_from_name"], "Sara Nazari")

    def test_mid_flight_change_leaves_memory_stale(self):
        # M-P5 race: a visit edited AFTER the snapshot leaves session.updated_at > memory freshness.
        patient = _patient()
        s1 = _session(updated_at=datetime(2026, 6, 7, tzinfo=timezone.utc))
        snapshot = memory_build_snapshot(patient, [s1], now=datetime(2026, 6, 7, tzinfo=timezone.utc))
        apply_patient_memory_output(
            patient,
            {"summary": "AI", "history": {"snapshot": "s", "sections": [{"label": "a", "body": "b"}]}, "source": "ai:x"},
            "pro", snapshot=snapshot,
        )
        # Now the visit changes after the build started.
        s1.updated_at = datetime(2026, 6, 8, tzinfo=timezone.utc)
        self.assertTrue(patient_memory_is_stale(patient, [s1]))


class MemoryPayloadTests(unittest.TestCase):
    def test_payload_omits_display_name(self):
        # M-P9(b): the patient's name is never sent to the memory model.
        patient = _patient(name="نگار محمدی")
        payload = build_patient_memory_job_input(patient, [_session()], "pro")
        self.assertNotIn("displayName", payload["patient"])
        # And the name token must not appear anywhere in the serialized patient context.
        import json
        self.assertNotIn("نگار", json.dumps(payload["patient"], ensure_ascii=False))


class TierGateTests(unittest.TestCase):
    def test_matches_tier(self):
        # M-P12: prior-tier content is not served after a flip; unknown mode matches (legacy).
        self.assertTrue(memory_matches_tier(_patient(memory={"mode": "pro"}), "pro"))
        self.assertFalse(memory_matches_tier(_patient(memory={"mode": "pro"}), "basic"))
        self.assertFalse(memory_matches_tier(_patient(memory={"mode": "basic"}), "pro"))
        self.assertTrue(memory_matches_tier(_patient(memory={}), "basic"))


class LotStripTests(unittest.TestCase):
    def test_strips_labeled_and_bare_lots(self):
        # Q-6: lot/batch tokens never reach the patient through a prefilled caption.
        self.assertEqual(_strip_lot_tokens("Botox vial, lot A1234B"), "Botox vial")
        self.assertEqual(_strip_lot_tokens("Restylane vial batch#77A21"), "Restylane vial")
        self.assertIsNone(_strip_lot_tokens("lot: XY-9981"))

    def test_preserves_ordinary_captions_and_doses(self):
        self.assertEqual(_strip_lot_tokens("After photo of left cheek"), "After photo of left cheek")
        self.assertEqual(_strip_lot_tokens("Voluma 0.3 mL"), "Voluma 0.3 mL")
        self.assertIsNone(_strip_lot_tokens(""))


class CuratedTreatmentOverlayTests(unittest.TestCase):
    def test_reads_overlaid_product(self):
        # M-P4: a clinician-corrected product reaches the share's "what we did" line.
        session = _session(
            treatments=[{"treatmentKey": "k1", "area": "cheek", "product": "Voluma", "brand": "Allergan"}],
            overlay=[{"op": "edit", "treatmentKey": "k1", "field": "product", "value": "Restylane"}],
        )
        lines = _curated_treatment_lines(session, include_brands=False)
        self.assertEqual(lines, ["cheek — Restylane"])


class ShareStalenessTests(unittest.TestCase):
    def _share(self, *, status=SHARE_STATUS_ACTIVE, created="2026-06-10T00:00:00+00:00"):
        from types import SimpleNamespace
        return SimpleNamespace(
            status=status,
            expires_at=None,
            created_at=datetime.fromisoformat(created),
        )

    def test_stale_when_source_changed_after_share(self):
        # Q-4: a report correction after the share was frozen marks it stale (needs-attention).
        share = self._share()
        self.assertTrue(_share_is_stale(share, datetime(2026, 6, 11, tzinfo=timezone.utc)))
        self.assertFalse(_share_is_stale(share, datetime(2026, 6, 9, tzinfo=timezone.utc)))

    def test_revoked_share_never_stale(self):
        share = self._share(status=SHARE_STATUS_REVOKED)
        self.assertFalse(_share_is_stale(share, datetime(2026, 6, 30, tzinfo=timezone.utc)))


if __name__ == "__main__":
    unittest.main()
