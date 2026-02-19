from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str
    organization_id: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class OrgSelectionRequest(BaseModel):
    refresh_token: str
    organization_id: str


class UserSummary(BaseModel):
    id: str
    tenant_id: str | None
    organization_id: str | None
    org_role: str | None
    platform_role: str | None
    roles: list[str]


class AuthTokens(BaseModel):
    access_token: str | None
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserSummary
    requires_org_selection: bool = False
    organizations: list[dict] = []
