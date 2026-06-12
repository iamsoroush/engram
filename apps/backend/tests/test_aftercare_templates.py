import unittest
import uuid
from datetime import datetime, timezone

from app.models import AftercareTemplate
from app.services.aftercare_templates import _normalize_procedure_type, aftercare_template_payload


def _template() -> AftercareTemplate:
    template = AftercareTemplate()
    template.id = uuid.uuid4()
    template.tenant_id = uuid.uuid4()
    template.name = "Botox aftercare"
    template.procedure_type = "botox"
    template.body = "Avoid lying down for 4 hours."
    template.is_active = True
    template.created_at = datetime(2026, 6, 12, tzinfo=timezone.utc)
    template.updated_at = template.created_at
    return template


class NormalizeProcedureTypeTests(unittest.TestCase):
    def test_lowercases_and_strips(self):
        self.assertEqual(_normalize_procedure_type("  Botox  "), "botox")

    def test_blank_becomes_none(self):
        self.assertIsNone(_normalize_procedure_type("   "))
        self.assertIsNone(_normalize_procedure_type(None))


class AftercareTemplatePayloadTests(unittest.TestCase):
    """AES-702: the serialized shape the frontend Settings surface consumes."""

    def test_payload_shape(self):
        payload = aftercare_template_payload(_template())
        self.assertEqual(payload["name"], "Botox aftercare")
        self.assertEqual(payload["procedureType"], "botox")
        self.assertEqual(payload["body"], "Avoid lying down for 4 hours.")
        self.assertTrue(payload["isActive"])
        self.assertEqual(set(payload.keys()), {"id", "tenantId", "name", "procedureType", "body", "isActive", "createdAt", "updatedAt"})


if __name__ == "__main__":
    unittest.main()
