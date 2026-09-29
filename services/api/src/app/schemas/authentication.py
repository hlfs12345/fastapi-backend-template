from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, SecretStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=1024)
    tenant_slug: str = Field(min_length=3, max_length=63, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class RefreshRequest(BaseModel):
    refresh_token: SecretStr = Field(min_length=64, max_length=512)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class AuthenticatedContextResponse(BaseModel):
    user_id: UUID
    tenant_id: UUID
    tenant_user_id: UUID
