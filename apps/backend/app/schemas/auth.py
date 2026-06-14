from pydantic import BaseModel, ConfigDict, Field


class DevLoginRequest(BaseModel):
    # `therapist-b` is a second therapist persona so the therapy tenant's federated caseloads
    # (a clinician sees only their own clients) are demonstrable side-by-side.
    persona: str = Field(pattern="^(doctor|assistant|admin|patient-preview|therapist-b)$")
    # Dev-only tenant selector: tier picks the aesthetics Pro/Basic demo tenants; `therapy` selects
    # the single-plan therapy demo tenant (vertical = therapy).
    tier: str = Field(default="pro", pattern="^(basic|pro|therapy)$")


class TenantSettingsUpdate(BaseModel):
    # Language preferences. transcription: "auto" | fa | en | ar. report: fa | en | ar, or
    # null/"" to follow the report template default. Only provided keys are changed.
    transcriptionLanguage: str | None = None
    reportLanguage: str | None = None
    # Fuzzy-match auto-apply line (H3): "strict" | "balanced" | "lenient".
    matchStrictness: str | None = None
    # Multi-seat role permissions (AES-905): per non-owner role preset, e.g.
    # {"assistant": "reassign", "doctor": "contribute"}. Each value ∈ contribute | reassign | full.
    # Only provided roles change; unknown roles/presets are rejected (400). Admin-only at the route.
    rolePermissions: dict[str, str] | None = None


class LoginRequest(BaseModel):
    email: str
    password: str
    tenant_id: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str = Field(alias="refreshToken")

    model_config = ConfigDict(populate_by_name=True)


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, alias="refreshToken")

    model_config = ConfigDict(populate_by_name=True)


class UserProfile(BaseModel):
    id: str
    email: str
    display_name: str | None = Field(alias="displayName")
    persona: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class TenantProfile(BaseModel):
    id: str
    name: str
    tier: str = "pro"
    transcriptionLanguage: str = "auto"
    reportLanguage: str | None = None
    matchStrictness: str = "strict"
    # A0 — vertical + the presentation label for its report-required work-unit ("Session" for clinics).
    vertical: str = "clinic"
    encounterLabel: str = "Session"
    # Multi-seat role permissions (AES-905): effective per non-owner role preset (defaults merged
    # with the tenant's overrides). The client uses it to show read-only/owner-only affordances;
    # the backend still enforces. Owner + admin are always "full" and aren't listed here.
    rolePermissions: dict[str, str] = Field(default_factory=dict)


class MembershipProfile(BaseModel):
    tenant_id: str = Field(alias="tenantId")
    role: str

    model_config = ConfigDict(populate_by_name=True)


class AuthResponse(BaseModel):
    access_token: str = Field(alias="accessToken")
    refresh_token: str = Field(alias="refreshToken")
    user: UserProfile
    tenant: TenantProfile
    memberships: list[MembershipProfile]

    model_config = ConfigDict(populate_by_name=True)


class MeResponse(BaseModel):
    user: UserProfile
    tenant: TenantProfile
    memberships: list[MembershipProfile]


class RefreshResponse(BaseModel):
    access_token: str = Field(alias="accessToken")
    refresh_token: str = Field(alias="refreshToken")

    model_config = ConfigDict(populate_by_name=True)
