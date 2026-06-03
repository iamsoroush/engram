from pydantic import BaseModel, ConfigDict, Field


class DevLoginRequest(BaseModel):
    persona: str = Field(pattern="^(doctor|assistant|admin|patient-preview)$")


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
