import json
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models import PatientShare
from app.services.patient_surface import (
    SHARE_SCHEMA_VERSION,
    _curated_aftercare,
    _curated_sections,
    _effective_status,
    _is_expired,
    _is_publicly_readable,
    _public_content,
)


def _content() -> dict:
    return {
        "schemaVersion": SHARE_SCHEMA_VERSION,
        "clinicName": "Engram Demo Clinic",
        "patientName": "Sara Nazari",
        "title": "Your Botox visit",
        "visitDate": "2026-06-12T10:00:00+00:00",
        "sections": [{"label": "Visit", "body": "Forehead Botox performed."}],
        "media": [{"captureId": "cap-abc", "caption": "Before"}],
        "aftercare": {"templateId": None, "name": "Botox aftercare", "body": "Avoid lying down for 4 hours."},
    }


def _share(*, status="active", expires_at=None, content=None) -> PatientShare:
    share = PatientShare()
    share.id = uuid.uuid4()
    share.tenant_id = uuid.uuid4()
    share.patient_id = uuid.uuid4()
    share.session_id = None
    share.token = "tok123"
    share.payload_type = "report_aftercare"
    share.status = status
    share.content = content if content is not None else _content()
    share.created_at = datetime(2026, 6, 12, tzinfo=timezone.utc)
    share.updated_at = share.created_at
    share.expires_at = expires_at
    share.revoked_at = None
    share.revoked_by_user_id = None
    return share


class CuratedSectionsTests(unittest.TestCase):
    def test_drops_empty_body_sections(self):
        sections = [SimpleNamespace(label="Visit", body="Botox."), SimpleNamespace(label="Empty", body="  ")]
        curated = _curated_sections(sections)
        self.assertEqual(curated, [{"label": "Visit", "body": "Botox."}])


class CuratedAftercareTests(unittest.TestCase):
    def test_inline_aftercare_without_template(self):
        result = _curated_aftercare(None, tenant_id=uuid.uuid4(), aftercare=SimpleNamespace(template_id=None, name="Care", body="Do this."))
        self.assertEqual(result, {"templateId": None, "name": "Care", "body": "Do this."})

    def test_none_aftercare_is_none(self):
        self.assertIsNone(_curated_aftercare(None, tenant_id=uuid.uuid4(), aftercare=None))

    def test_blank_inline_body_is_none(self):
        self.assertIsNone(_curated_aftercare(None, tenant_id=uuid.uuid4(), aftercare=SimpleNamespace(template_id=None, name="X", body="   ")))


class EffectiveStatusTests(unittest.TestCase):
    def test_active(self):
        self.assertEqual(_effective_status(_share()), "active")
        self.assertTrue(_is_publicly_readable(_share()))

    def test_revoked(self):
        share = _share(status="revoked")
        self.assertEqual(_effective_status(share), "revoked")
        self.assertFalse(_is_publicly_readable(share))

    def test_expired(self):
        past = datetime.now(timezone.utc) - timedelta(days=1)
        share = _share(expires_at=past)
        self.assertTrue(_is_expired(share))
        self.assertEqual(_effective_status(share), "expired")
        self.assertFalse(_is_publicly_readable(share))

    def test_future_expiry_is_active(self):
        future = datetime.now(timezone.utc) + timedelta(days=5)
        self.assertFalse(_is_expired(_share(expires_at=future)))
        self.assertTrue(_is_publicly_readable(_share(expires_at=future)))


class PublicContentTests(unittest.TestCase):
    """AES-401/403: the public payload is the curated snapshot only — internals never appear."""

    def test_projects_curated_payload_with_media_urls(self):
        payload = _public_content(_share())
        self.assertEqual(payload["patientName"], "Sara Nazari")
        self.assertEqual(payload["clinic"]["name"], "Engram Demo Clinic")
        self.assertEqual([s["label"] for s in payload["sections"]], ["Visit"])
        self.assertEqual(payload["media"][0]["url"], "/api/v1/share/tok123/media/cap-abc")
        self.assertEqual(payload["aftercare"]["name"], "Botox aftercare")

    def test_withholds_clinical_internals(self):
        # The snapshot has no national ID / lots / raw captures, so they cannot leak.
        serialized = json.dumps(_public_content(_share()))
        for withheld in ("nationalId", "national_id", "lot", "rawCapture", "transcript"):
            self.assertNotIn(withheld, serialized)

    def test_keys_are_a_fixed_curated_set(self):
        payload = _public_content(_share())
        self.assertEqual(
            set(payload.keys()),
            {"schemaVersion", "payloadType", "status", "clinic", "patientName", "title", "visitDate", "language", "sections", "treatments", "media", "aftercare", "createdAt", "expiresAt"},
        )


if __name__ == "__main__":
    unittest.main()
