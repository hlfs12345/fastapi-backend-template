from uuid import UUID

from pydantic import BaseModel, Field


class PermissionResponse(BaseModel):
    code: str
    description: str


class RoleCreateRequest(BaseModel):
    key: str = Field(
        min_length=1,
        max_length=63,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    permission_codes: set[str] = Field(default_factory=set)


class RoleUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    permission_codes: set[str] = Field(default_factory=set)


class RoleResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    key: str
    name: str
    description: str | None
    is_system: bool
    permission_codes: list[str]
