from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class TenantUserRoleResponse(BaseModel):
    id: UUID
    key: str
    name: str
    is_system: bool


class TenantUserResponse(BaseModel):
    id: UUID
    user_id: UUID
    email: EmailStr
    joined_at: datetime
    deactivated_at: datetime | None
    is_active: bool
    roles: list[TenantUserRoleResponse]


class TenantUserUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_ids: set[UUID] | None = None
