"""Self-serve clinic sign-up unit tests (AES launch gap A): slug generation, request validation,
the founding ``owner`` role's full capture+admin reach, and that existing roles are unchanged.

Mocked-DB style matching the suite; the DB-backed happy path (real tenant+owner rows + JWTs) is
exercised by the dev-stack sign-up smoke in the build report.
"""

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.auth import service
from app.auth.dependencies import staff_or_admin_required, staff_required
from app.auth.service import _slugify, _unique_tenant_slug, register
from app.models import MembershipRole, Tenant, User
from app.services.permissions import FULL, role_permission_level


def _result(value):
    """A stand-in for ``db.execute(...)`` whose ``.scalar_one_or_none()`` returns ``value``."""
    row = MagicMock()
    row.scalar_one_or_none.return_value = value
    return row


class SlugifyTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(_slugify("Glow Aesthetics Clinic"), "glow-aesthetics-clinic")

    def test_trims_and_collapses_punctuation(self):
        self.assertEqual(_slugify("  Derma  &  Co. "), "derma-co")

    def test_non_latin_falls_back_to_clinic(self):
        # Persian clinic names have no ascii slug; the internal slug just needs to be unique.
        self.assertEqual(_slugify("کلینیک زیبایی"), "clinic")


class UniqueSlugTests(unittest.TestCase):
    def test_first_candidate_is_free(self):
        db = MagicMock()
        db.execute.return_value = _result(None)
        self.assertEqual(_unique_tenant_slug(db, "Glow"), "glow")

    def test_appends_numeric_suffix_on_collision(self):
        db = MagicMock()
        db.execute.side_effect = [_result(uuid.uuid4()), _result(None)]  # base taken, base-2 free
        self.assertEqual(_unique_tenant_slug(db, "Glow"), "glow-2")


class RegisterValidationTests(unittest.TestCase):
    def _db(self, existing_user=None):
        db = MagicMock()
        db.execute.return_value = _result(existing_user)
        return db

    def test_rejects_invalid_email(self):
        with self.assertRaises(HTTPException) as ctx:
            register(self._db(), clinic_name="Glow", full_name="Dr A", email="not-an-email", password="longenough", app_language=None)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_rejects_short_password(self):
        with self.assertRaises(HTTPException) as ctx:
            register(self._db(), clinic_name="Glow", full_name="Dr A", email="a@b.com", password="short", app_language=None)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_rejects_blank_clinic_name(self):
        with self.assertRaises(HTTPException) as ctx:
            register(self._db(), clinic_name="   ", full_name="Dr A", email="a@b.com", password="longenough", app_language=None)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_rejects_duplicate_email(self):
        db = self._db(existing_user=uuid.uuid4())
        with self.assertRaises(HTTPException) as ctx:
            register(db, clinic_name="Glow", full_name="Dr A", email="a@b.com", password="longenough", app_language=None)
        self.assertEqual(ctx.exception.status_code, 409)


class RegisterHappyPathTests(unittest.TestCase):
    def test_creates_tenant_user_and_owner_membership(self):
        db = MagicMock()
        db.execute.return_value = _result(None)  # email free; slug free
        with patch.object(service, "issue_tokens", return_value=("access", "refresh")), patch.object(
            service, "profile_response", return_value="PROFILE"
        ):
            out = register(db, clinic_name="Glow Skin", full_name="Dr. A", email="DR@A.com", password="longenough", app_language="fa")

        self.assertEqual(out, "PROFILE")
        added = [call.args[0] for call in db.add.call_args_list]
        tenant = next(obj for obj in added if isinstance(obj, Tenant))
        user = next(obj for obj in added if isinstance(obj, User))
        membership = next(obj for obj in added if isinstance(obj, service.TenantMembership))
        # A founding owner of an aesthetics clinic, started on Basic, in the language they signed up in.
        self.assertEqual(membership.role, MembershipRole.owner)
        self.assertEqual(tenant.vertical, "aesthetics")
        self.assertEqual(tenant.tier, "basic")
        self.assertEqual(tenant.app_language, "fa")
        self.assertEqual(user.email, "dr@a.com")  # normalized to lowercase
        db.commit.assert_called_once()

    def test_unknown_language_defaults_to_persian(self):
        db = MagicMock()
        db.execute.return_value = _result(None)
        with patch.object(service, "issue_tokens", return_value=("a", "r")), patch.object(service, "profile_response", return_value="P"):
            register(db, clinic_name="Glow", full_name="Dr A", email="a@b.com", password="longenough", app_language="zz")
        tenant = next(obj for obj in (call.args[0] for call in db.add.call_args_list) if isinstance(obj, Tenant))
        self.assertEqual(tenant.app_language, "fa")


class OwnerRoleReachTests(unittest.TestCase):
    """The additive ``owner`` role is a full superset; existing roles keep their semantics."""

    def test_owner_is_always_full_in_permissions(self):
        self.assertEqual(role_permission_level(frozenset({"owner"}), {}), FULL)

    def test_owner_passes_the_staff_capture_gate(self):
        principal = SimpleNamespace(roles=frozenset({"owner"}))
        self.assertIs(staff_required(principal=principal), principal)

    def test_owner_passes_the_admin_gate(self):
        principal = SimpleNamespace(roles=frozenset({"owner"}))
        self.assertIs(staff_or_admin_required(principal=principal), principal)

    def test_admin_still_cannot_capture(self):
        # Regression guard: owner did not loosen the existing admin = read-only-capture rule.
        principal = SimpleNamespace(roles=frozenset({"admin"}))
        with self.assertRaises(HTTPException) as ctx:
            staff_required(principal=principal)
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
