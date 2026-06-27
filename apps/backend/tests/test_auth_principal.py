"""Request-time authorization is derived from the LIVE membership, not the token's roles claim, so
disabling a member or changing their role takes effect on the next request (not at token expiry)."""

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.auth import dependencies
from app.auth.dependencies import get_current_principal
from app.models import MembershipRole, MembershipStatus, TenantStatus, User, UserStatus


def _creds():
    return SimpleNamespace(credentials="access-token")


class GetCurrentPrincipalTests(unittest.TestCase):
    def _run(self, membership):
        user = SimpleNamespace(id=uuid.uuid4(), status=UserStatus.active)
        tenant = SimpleNamespace(id=uuid.uuid4(), status=TenantStatus.active)
        db = MagicMock()
        db.get.side_effect = lambda model, _pk: user if model is User else tenant
        row = MagicMock()
        row.scalar_one_or_none.return_value = membership
        db.execute.return_value = row
        payload = {"sub": str(user.id), "tenant_id": str(tenant.id), "jti": "j1"}
        with patch.object(dependencies, "decode_jwt", return_value=payload):
            return get_current_principal(credentials=_creds(), db=db)

    def test_active_membership_derives_role(self):
        principal = self._run(SimpleNamespace(role=MembershipRole.doctor, status=MembershipStatus.active))
        self.assertEqual(principal.roles, frozenset({"doctor"}))

    def test_disabled_member_is_rejected(self):
        # A disabled member has no active membership → their existing access token is rejected.
        with self.assertRaises(HTTPException) as ctx:
            self._run(None)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_role_change_is_reflected_live(self):
        # The live membership wins over whatever role the token was minted with.
        principal = self._run(SimpleNamespace(role=MembershipRole.admin, status=MembershipStatus.active))
        self.assertEqual(principal.roles, frozenset({"admin"}))


if __name__ == "__main__":
    unittest.main()
