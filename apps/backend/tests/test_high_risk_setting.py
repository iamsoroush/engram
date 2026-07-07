"""High-risk-clinic tenant setting (session-layout-diet, AES-1304): write path + profile serialization.

DB-free: a fake db.get serves a tenant stub; audit is patched. Confirms the setting round-trips through
update_tenant_settings and surfaces on the TenantProfile the client reads (to pin the safety panel).
"""
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from app.auth import service as auth_service


def _tenant(high_risk=False):
    return SimpleNamespace(
        id=uuid.uuid4(),
        name="Clinic",
        tier="pro",
        transcription_language="auto",
        report_language=None,
        app_language="en",
        match_strictness="strict",
        share_include_brands=False,
        high_risk_clinic=high_risk,
        vertical="clinic",
        role_permissions={},
    )


class _Db:
    def __init__(self, tenant):
        self._tenant = tenant

    def get(self, _model, _pk):
        return self._tenant

    def commit(self):
        pass

    def refresh(self, _obj):
        pass


def _principal():
    return SimpleNamespace(tenant_id=uuid.uuid4(), user_id=uuid.uuid4(), roles=frozenset({"owner"}))


class HighRiskSettingTests(unittest.TestCase):
    def test_profile_exposes_high_risk_flag(self):
        profile = auth_service.tenant_profile(_tenant(high_risk=True))
        self.assertTrue(profile.highRiskClinic)

    def test_profile_defaults_off(self):
        self.assertFalse(auth_service.tenant_profile(_tenant()).highRiskClinic)

    def test_update_sets_the_flag(self):
        tenant = _tenant(high_risk=False)
        with patch.object(auth_service, "audit"):
            profile = auth_service.update_tenant_settings(_Db(tenant), _principal(), provided={"highRiskClinic": True})
        self.assertTrue(tenant.high_risk_clinic)
        self.assertTrue(profile.highRiskClinic)

    def test_update_leaves_flag_untouched_when_not_provided(self):
        tenant = _tenant(high_risk=True)
        with patch.object(auth_service, "audit"):
            auth_service.update_tenant_settings(_Db(tenant), _principal(), provided={"shareIncludeBrands": True})
        self.assertTrue(tenant.high_risk_clinic)  # only provided keys change


if __name__ == "__main__":
    unittest.main()
