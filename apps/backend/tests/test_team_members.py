"""Clinic member-management unit tests (launch gap A follow-up): role/validation guards on create +
update, owner/self protection, and that the Team gate admits owner/admin only. Mocked-DB style; the
DB-backed happy path is covered by the dev-stack Team smoke."""

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.auth import service as auth_service
from app.auth.dependencies import tenant_admin_required
from app.auth.service import set_tenant_plan
from app.models import MembershipRole, MembershipStatus, TenantMembership, User
from app.services.team import create_team_member, update_team_member


def _result(value):
    row = MagicMock()
    row.scalar_one_or_none.return_value = value
    return row


def _principal():
    return SimpleNamespace(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), roles=frozenset({"owner"}))


class CreateMemberTests(unittest.TestCase):
    def _db_new_email(self):
        # No user with that email exists (so the new-user path runs).
        db = MagicMock()
        db.execute.return_value = _result(None)
        return db

    def test_rejects_non_assignable_role(self):
        for bad in ("owner", "patient", "wizard"):
            with self.assertRaises(HTTPException) as ctx:
                create_team_member(self._db_new_email(), _principal(), full_name="A", email="a@b.com", password="longenough", role=bad)
            self.assertEqual(ctx.exception.status_code, 400)

    def test_new_user_requires_password(self):
        for pw in (None, "short"):
            with self.assertRaises(HTTPException) as ctx:
                create_team_member(self._db_new_email(), _principal(), full_name="A", email="a@b.com", password=pw, role="doctor")
            self.assertEqual(ctx.exception.status_code, 400)

    def test_creates_new_user_and_membership(self):
        db = self._db_new_email()
        principal = _principal()
        out = create_team_member(db, principal, full_name="Dr. B", email="DR.B@x.com", password="longenough", role="assistant")
        added = [call.args[0] for call in db.add.call_args_list]
        user = next(obj for obj in added if isinstance(obj, User))
        membership = next(obj for obj in added if isinstance(obj, TenantMembership))
        self.assertEqual(user.email, "dr.b@x.com")  # normalized
        self.assertEqual(membership.role, MembershipRole.assistant)
        self.assertEqual(membership.tenant_id, principal.tenant_id)
        self.assertEqual(out["role"], "assistant")
        self.assertTrue(out["created"])
        db.commit.assert_called_once()

    def test_existing_user_added_across_clinics_without_password(self):
        existing = SimpleNamespace(id=uuid.uuid4(), full_name="Existing Doc", email="exist@x.com")
        db = MagicMock()
        # 1) user lookup → found; 2) membership-exists check → none in this tenant
        db.execute.side_effect = [_result(existing), _result(None)]
        out = create_team_member(db, _principal(), full_name="ignored", email="exist@x.com", password=None, role="doctor")
        self.assertFalse(out["created"])
        self.assertEqual(out["email"], "exist@x.com")
        added = [call.args[0] for call in db.add.call_args_list]
        membership = next(obj for obj in added if isinstance(obj, TenantMembership))
        self.assertEqual(membership.role, MembershipRole.doctor)
        # No new User is created for an existing account.
        self.assertFalse(any(isinstance(obj, User) for obj in added))

    def test_existing_user_already_member_conflicts(self):
        existing = SimpleNamespace(id=uuid.uuid4(), full_name="X", email="x@x.com")
        db = MagicMock()
        db.execute.side_effect = [_result(existing), _result(uuid.uuid4())]  # membership already exists here
        with self.assertRaises(HTTPException) as ctx:
            create_team_member(db, _principal(), full_name="X", email="x@x.com", password=None, role="doctor")
        self.assertEqual(ctx.exception.status_code, 409)


class UpdateMemberTests(unittest.TestCase):
    def _db_with_member(self, *, role=MembershipRole.doctor, status=MembershipStatus.active):
        db = MagicMock()
        membership = SimpleNamespace(role=role, status=status, updated_at=None)
        db.execute.return_value = _result(membership)
        db.get.return_value = SimpleNamespace(id=uuid.uuid4(), full_name="X", email="x@y.com")
        return db, membership

    def test_owner_is_protected(self):
        db, _ = self._db_with_member(role=MembershipRole.owner)
        with self.assertRaises(HTTPException) as ctx:
            update_team_member(db, _principal(), user_id=str(uuid.uuid4()), role="doctor", status_value=None)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_cannot_change_self(self):
        db, _ = self._db_with_member()
        principal = _principal()
        with self.assertRaises(HTTPException) as ctx:
            update_team_member(db, principal, user_id=str(principal.user_id), role=None, status_value="disabled")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_missing_member_is_404(self):
        db = MagicMock()
        db.execute.return_value = _result(None)
        with self.assertRaises(HTTPException) as ctx:
            update_team_member(db, _principal(), user_id=str(uuid.uuid4()), role="doctor", status_value=None)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_rejects_bad_status(self):
        db, _ = self._db_with_member()
        with self.assertRaises(HTTPException) as ctx:
            update_team_member(db, _principal(), user_id=str(uuid.uuid4()), role=None, status_value="banished")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_applies_role_and_status(self):
        db, membership = self._db_with_member()
        out = update_team_member(db, _principal(), user_id=str(uuid.uuid4()), role="admin", status_value="disabled")
        self.assertEqual(membership.role, MembershipRole.admin)
        self.assertEqual(membership.status, MembershipStatus.disabled)
        self.assertEqual(out["status"], "disabled")
        db.commit.assert_called_once()


class TeamGateTests(unittest.TestCase):
    def test_owner_and_admin_pass(self):
        for role in ("owner", "admin"):
            principal = SimpleNamespace(roles=frozenset({role}))
            self.assertIs(tenant_admin_required(principal=principal), principal)

    def test_clinical_staff_are_blocked(self):
        for role in ("doctor", "assistant"):
            principal = SimpleNamespace(roles=frozenset({role}))
            with self.assertRaises(HTTPException) as ctx:
                tenant_admin_required(principal=principal)
            self.assertEqual(ctx.exception.status_code, 403)


class PlanSwitchTests(unittest.TestCase):
    def test_rejects_unknown_tier(self):
        with self.assertRaises(HTTPException) as ctx:
            set_tenant_plan(MagicMock(), _principal(), tier="enterprise")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_switches_tier(self):
        db = MagicMock()
        tenant = SimpleNamespace(id=uuid.uuid4(), tier="basic")
        db.get.return_value = tenant
        with patch.object(auth_service, "tenant_profile", return_value="PROFILE"):
            out = set_tenant_plan(db, _principal(), tier="pro")
        self.assertEqual(out, "PROFILE")
        self.assertEqual(tenant.tier, "pro")
        db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
