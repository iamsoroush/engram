"""Multi-seat (E9) unit tests: role-permission resolution, ownership grading, attribution, and the
AES-906 policy-deferred reassignment suggestion. Pure functions only (mocked DB), matching the
suite's no-fixture style; the DB-backed worklist + route enforcement are covered by the manual
dev-stack scenarios in the build report."""

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from app.services.attribution import attribution_payload
from app.services.permissions import (
    CONTRIBUTE,
    DEFAULT_ROLE_PERMISSIONS,
    FULL,
    REASSIGN,
    can_edit,
    can_reassign,
    resolve_role_permissions,
    role_permission_level,
    session_permission_for_roles,
    user_can_reassign_session,
)


class ResolveRolePermissionsTests(unittest.TestCase):
    def test_empty_falls_back_to_permissive_defaults(self):
        self.assertEqual(resolve_role_permissions(None), DEFAULT_ROLE_PERMISSIONS)
        self.assertEqual(resolve_role_permissions({}), DEFAULT_ROLE_PERMISSIONS)
        # Default = contribute open · assistant (the receptionist seat here) can reassign · edit = owner.
        self.assertEqual(DEFAULT_ROLE_PERMISSIONS, {"doctor": CONTRIBUTE, "assistant": REASSIGN})

    def test_valid_override_applies(self):
        resolved = resolve_role_permissions({"assistant": "full"})
        self.assertEqual(resolved["assistant"], FULL)
        self.assertEqual(resolved["doctor"], CONTRIBUTE)  # untouched

    def test_tighten_is_honored(self):
        self.assertEqual(resolve_role_permissions({"assistant": "contribute"})["assistant"], CONTRIBUTE)

    def test_unknown_role_or_preset_is_ignored_never_expands(self):
        # A bogus preset or non-configurable role can never silently grant access.
        resolved = resolve_role_permissions({"assistant": "superuser", "receptionist": "full", "admin": "contribute"})
        self.assertEqual(resolved["assistant"], REASSIGN)  # fell back to default
        self.assertNotIn("receptionist", resolved)
        self.assertNotIn("admin", resolved)


class RolePermissionLevelTests(unittest.TestCase):
    def setUp(self):
        self.perms = dict(DEFAULT_ROLE_PERMISSIONS)

    def test_admin_is_always_full(self):
        self.assertEqual(role_permission_level(frozenset({"admin"}), {}), FULL)
        # Even if a stored preset says otherwise, admin wins.
        self.assertEqual(role_permission_level(frozenset({"admin"}), {"admin": CONTRIBUTE}), FULL)

    def test_assistant_default_is_reassign(self):
        self.assertEqual(role_permission_level(frozenset({"assistant"}), self.perms), REASSIGN)

    def test_non_owner_doctor_default_is_contribute(self):
        self.assertEqual(role_permission_level(frozenset({"doctor"}), self.perms), CONTRIBUTE)

    def test_unknown_role_gets_contribute_floor(self):
        self.assertEqual(role_permission_level(frozenset({"intern"}), self.perms), CONTRIBUTE)

    def test_highest_of_multiple_roles_wins(self):
        self.assertEqual(role_permission_level(frozenset({"doctor", "assistant"}), self.perms), REASSIGN)


class SessionPermissionForRolesTests(unittest.TestCase):
    def test_owner_is_full_regardless_of_role_policy(self):
        # An owner whose role is only "contribute" still has full rights on their own session.
        level = session_permission_for_roles(is_owner=True, roles=frozenset({"doctor"}), role_permissions={"doctor": CONTRIBUTE})
        self.assertEqual(level, FULL)
        self.assertTrue(can_edit(level))

    def test_non_owner_follows_policy(self):
        level = session_permission_for_roles(is_owner=False, roles=frozenset({"assistant"}), role_permissions=DEFAULT_ROLE_PERMISSIONS)
        self.assertEqual(level, REASSIGN)
        self.assertTrue(can_reassign(level))
        self.assertFalse(can_edit(level))


class PresetThresholdTests(unittest.TestCase):
    def test_can_reassign_ladder(self):
        self.assertFalse(can_reassign(CONTRIBUTE))
        self.assertTrue(can_reassign(REASSIGN))
        self.assertTrue(can_reassign(FULL))

    def test_can_edit_only_full(self):
        self.assertFalse(can_edit(CONTRIBUTE))
        self.assertFalse(can_edit(REASSIGN))
        self.assertTrue(can_edit(FULL))


class UserCanReassignSessionTests(unittest.TestCase):
    def test_owner_can_always_reassign_own_session(self):
        owner = uuid.uuid4()
        session = SimpleNamespace(tenant_id=uuid.uuid4(), created_by_user_id=owner)
        # Owner short-circuits before any DB lookup.
        self.assertTrue(user_can_reassign_session(object(), session=session, user_id=owner))

    def test_none_user_cannot_reassign(self):
        session = SimpleNamespace(tenant_id=uuid.uuid4(), created_by_user_id=uuid.uuid4())
        self.assertFalse(user_can_reassign_session(object(), session=session, user_id=None))

    def test_non_owner_assistant_can_reassign_by_default_policy(self):
        session = SimpleNamespace(tenant_id=uuid.uuid4(), created_by_user_id=uuid.uuid4())
        with patch("app.services.permissions.roles_for_user_in_tenant", return_value=frozenset({"assistant"})), patch(
            "app.services.permissions.tenant_role_permissions", return_value=DEFAULT_ROLE_PERMISSIONS
        ):
            self.assertTrue(user_can_reassign_session(object(), session=session, user_id=uuid.uuid4()))

    def test_non_owner_assistant_cannot_reassign_when_tightened(self):
        session = SimpleNamespace(tenant_id=uuid.uuid4(), created_by_user_id=uuid.uuid4())
        with patch("app.services.permissions.roles_for_user_in_tenant", return_value=frozenset({"assistant"})), patch(
            "app.services.permissions.tenant_role_permissions", return_value={"assistant": CONTRIBUTE}
        ):
            self.assertFalse(user_can_reassign_session(object(), session=session, user_id=uuid.uuid4()))

    def test_non_owner_doctor_cannot_reassign_by_default(self):
        session = SimpleNamespace(tenant_id=uuid.uuid4(), created_by_user_id=uuid.uuid4())
        with patch("app.services.permissions.roles_for_user_in_tenant", return_value=frozenset({"doctor"})), patch(
            "app.services.permissions.tenant_role_permissions", return_value=DEFAULT_ROLE_PERMISSIONS
        ):
            self.assertFalse(user_can_reassign_session(object(), session=session, user_id=uuid.uuid4()))


class PolicyDeferredSuggestionTests(unittest.TestCase):
    def test_policy_deferred_reassignment_becomes_owner_suggestion(self):
        from app.services.ai_jobs import suggested_reassignment_candidate

        session = SimpleNamespace(tenant_id=uuid.uuid4(), patient_id=uuid.uuid4())
        fake_match = {"decision": "matched", "patientId": str(uuid.uuid4()), "displayName": "Ms Ghasemi"}
        with patch("app.services.ai_jobs.match_patient_from_patient_information", return_value=fake_match):
            candidate = suggested_reassignment_candidate(
                object(),
                tenant_id=session.tenant_id,
                session=session,
                patient_information={"raw_mentioned_name": "خانم قاسمی"},
                policy_deferred=True,
            )
        self.assertEqual(candidate["decision"], "suggested_reassignment")
        self.assertTrue(candidate["policyDeferred"])
        self.assertFalse(candidate["appliedAutomatically"])
        self.assertIn("role can't reassign", candidate["reason"])

    def test_implicit_suggestion_is_not_policy_deferred(self):
        from app.services.ai_jobs import suggested_reassignment_candidate

        session = SimpleNamespace(tenant_id=uuid.uuid4(), patient_id=uuid.uuid4())
        fake_match = {"decision": "matched", "patientId": str(uuid.uuid4()), "displayName": "Ms Ghasemi"}
        with patch("app.services.ai_jobs.match_patient_from_patient_information", return_value=fake_match):
            candidate = suggested_reassignment_candidate(
                object(), tenant_id=session.tenant_id, session=session, patient_information={"raw_mentioned_name": "x"}
            )
        self.assertFalse(candidate["policyDeferred"])


class AttributionPayloadTests(unittest.TestCase):
    def test_none_user_id_returns_none(self):
        self.assertIsNone(attribution_payload(object(), None))

    def test_resolves_display_name_from_full_name(self):
        uid = uuid.uuid4()
        db = SimpleNamespace(get=lambda _model, _id: SimpleNamespace(full_name="Dr. Demo", email="d@x.io"))
        self.assertEqual(attribution_payload(db, uid), {"userId": str(uid), "displayName": "Dr. Demo"})

    def test_falls_back_to_email_then_none(self):
        uid = uuid.uuid4()
        db_email = SimpleNamespace(get=lambda _model, _id: SimpleNamespace(full_name=None, email="d@x.io"))
        self.assertEqual(attribution_payload(db_email, uid)["displayName"], "d@x.io")
        db_missing = SimpleNamespace(get=lambda _model, _id: None)
        self.assertEqual(attribution_payload(db_missing, uid), {"userId": str(uid), "displayName": None})
        # No db at all → id known, name unknown (not a crash).
        self.assertEqual(attribution_payload(None, uid), {"userId": str(uid), "displayName": None})


if __name__ == "__main__":
    unittest.main()
