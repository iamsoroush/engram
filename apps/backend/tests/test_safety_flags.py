import unittest
import uuid

from app.models import Patient, Session
from app.services.patient_safety import (
    drop_session_safety_flags,
    patient_safety_flags,
    patient_safety_flags_payload,
    safety_flag_key,
    session_detected_safety_flags,
    session_kept_safety_flags,
    sync_patient_safety_flags,
)


def _flag(kind: str, text: str, capture_ids=None) -> dict:
    return {"kind": kind, "text": text, "sourceCaptureIds": capture_ids or []}


def _session(metadata: dict) -> Session:
    session = Session()
    session.id = uuid.uuid4()
    session.extracted_metadata = metadata
    return session


def _patient(safety_flags=None) -> Patient:
    patient = Patient()
    patient.id = uuid.uuid4()
    patient.display_name = "Sara Nazari"
    patient.safety_flags = safety_flags  # may be None — the read path must coerce
    return patient


class SafetyFlagKeyTests(unittest.TestCase):
    def test_key_is_kind_plus_normalized_text(self):
        self.assertEqual(safety_flag_key("allergy", "به لیدوکائین حساسیت داره"), "allergy|به لیدوکائین حساسیت داره")

    def test_key_normalizes_whitespace_and_case(self):
        # Matches the frontend safetyFlagKey: trim + collapse whitespace + lowercase.
        self.assertEqual(
            safety_flag_key("contraindication", "  Pregnant —  avoid   Botox "),
            safety_flag_key("contraindication", "pregnant — avoid botox"),
        )


class SessionFlagReadTests(unittest.TestCase):
    def test_detected_flags_validated_and_keyed(self):
        session = _session(
            {
                "safety_flags": [
                    _flag("allergy", "به لیدوکائین حساسیت داره", ["c1"]),
                    _flag("bogus", "ignored"),  # unknown kind dropped
                    {"kind": "consent", "text": "   "},  # empty text dropped
                    {"kind": "consent", "text": "رضایت‌نامه گرفته شد"},
                ]
            }
        )
        detected = session_detected_safety_flags(session)
        self.assertEqual([f["kind"] for f in detected], ["allergy", "consent"])
        self.assertEqual(detected[0]["key"], safety_flag_key("allergy", "به لیدوکائین حساسیت داره"))
        self.assertEqual(detected[0]["sourceCaptureIds"], ["c1"])

    def test_kept_excludes_rejected(self):
        allergy_key = safety_flag_key("allergy", "حساسیت به پنی‌سیلین")
        session = _session(
            {
                "safety_flags": [
                    _flag("allergy", "حساسیت به پنی‌سیلین"),
                    _flag("consent", "رضایت‌نامه گرفته شد"),
                ],
                "rejected_safety_flags": [allergy_key],
            }
        )
        kept = session_kept_safety_flags(session)
        self.assertEqual([f["kind"] for f in kept], ["consent"])

    def test_missing_metadata_is_safe(self):
        self.assertEqual(session_detected_safety_flags(_session({})), [])
        self.assertEqual(session_kept_safety_flags(_session({})), [])


class PatientSyncTests(unittest.TestCase):
    def test_sync_persists_kept_flags_with_provenance(self):
        patient = _patient(None)  # never had flags — must coerce None
        session = _session({"safety_flags": [_flag("allergy", "حساسیت به لیدوکائین", ["c1"])]})
        sync_patient_safety_flags(patient, session)
        stored = patient_safety_flags(patient)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["kind"], "allergy")
        self.assertEqual(stored[0]["sourceSessionId"], str(session.id))
        self.assertIn("addedAt", stored[0])

    def test_rejection_removes_from_patient_on_resync(self):
        patient = _patient(None)
        key = safety_flag_key("allergy", "حساسیت به لیدوکائین")
        session = _session({"safety_flags": [_flag("allergy", "حساسیت به لیدوکائین")]})
        sync_patient_safety_flags(patient, session)
        self.assertEqual(len(patient_safety_flags(patient)), 1)
        # Clinician rejects it → re-sync drops it from the patient store.
        session.extracted_metadata["rejected_safety_flags"] = [key]
        sync_patient_safety_flags(patient, session)
        self.assertEqual(patient_safety_flags(patient), [])

    def test_resync_replaces_only_this_sessions_contribution(self):
        patient = _patient(None)
        s1 = _session({"safety_flags": [_flag("allergy", "حساسیت به لیدوکائین")]})
        s2 = _session({"safety_flags": [_flag("consent", "رضایت‌نامه گرفته شد")]})
        sync_patient_safety_flags(patient, s1)
        sync_patient_safety_flags(patient, s2)
        self.assertEqual({f["kind"] for f in patient_safety_flags(patient)}, {"allergy", "consent"})
        # A re-synthesis of s1 with a DIFFERENT flag replaces only s1's entry; s2's survives.
        s1.extracted_metadata["safety_flags"] = [_flag("contraindication", "باردار است")]
        sync_patient_safety_flags(patient, s1)
        kinds = {f["kind"] for f in patient_safety_flags(patient)}
        self.assertEqual(kinds, {"contraindication", "consent"})

    def test_drop_removes_only_that_sessions_contribution(self):
        # Mirrors assignment/reassignment: dropping one visit's contribution leaves others intact.
        patient = _patient(None)
        s1 = _session({"safety_flags": [_flag("allergy", "حساسیت به لیدوکائین")]})
        s2 = _session({"safety_flags": [_flag("consent", "رضایت‌نامه گرفته شد")]})
        sync_patient_safety_flags(patient, s1)
        sync_patient_safety_flags(patient, s2)
        drop_session_safety_flags(patient, s1.id)
        kinds = {f["kind"] for f in patient_safety_flags(patient)}
        self.assertEqual(kinds, {"consent"})

    def test_payload_dedupes_by_key(self):
        patient = _patient(None)
        same = _flag("allergy", "حساسیت به لیدوکائین")
        s1 = _session({"safety_flags": [same]})
        s2 = _session({"safety_flags": [same]})  # same flag, two visits
        sync_patient_safety_flags(patient, s1)
        sync_patient_safety_flags(patient, s2)
        payload = patient_safety_flags_payload(patient)
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["kind"], "allergy")
        self.assertNotIn("sourceSessionId", payload[0])  # payload is glanceable, no provenance


if __name__ == "__main__":
    unittest.main()
