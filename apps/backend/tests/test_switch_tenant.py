"""Clinic switch (B2): re-issue a session for another tenant the user actively belongs to."""

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.auth import service as auth_service
from app.auth.service import switch_tenant
from app.models import TenantStatus


def _principal():
    return SimpleNamespace(user=SimpleNamespace(id=uuid.uuid4()), user_id=uuid.uuid4(), tenant_id=uuid.uuid4())


class SwitchTenantTests(unittest.TestCase):
    def test_invalid_tenant_id(self):
        with self.assertRaises(HTTPException) as ctx:
            switch_tenant(MagicMock(), _principal(), tenant_id="not-a-uuid")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_non_member_is_forbidden(self):
        with patch.object(auth_service, "active_memberships", return_value=[]):
            with self.assertRaises(HTTPException) as ctx:
                switch_tenant(MagicMock(), _principal(), tenant_id=str(uuid.uuid4()))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_switches_to_a_member_clinic(self):
        target = uuid.uuid4()
        db = MagicMock()
        db.get.return_value = SimpleNamespace(status=TenantStatus.active)
        membership = SimpleNamespace(tenant_id=target)
        with patch.object(auth_service, "active_memberships", return_value=[membership]), patch.object(
            auth_service, "issue_tokens", return_value=("a", "r")
        ), patch.object(auth_service, "profile_response", return_value="PROFILE"):
            out = switch_tenant(db, _principal(), tenant_id=str(target))
        self.assertEqual(out, "PROFILE")
        db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
