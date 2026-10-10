from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class ContactStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DEACTIVATED = "DEACTIVATED"


class ContactStatusFilter(StrEnum):
    ACTIVE = "ACTIVE"
    DEACTIVATED = "DEACTIVATED"
    ALL = "ALL"


class ContactCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=1, max_length=32)


class ContactUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_update(self) -> "ContactUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Name cannot be null.")
        return self


class ContactSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=1, max_length=32)
    include_deactivated: bool = False

    @model_validator(mode="after")
    def validate_identifiers(self) -> "ContactSearchRequest":
        if self.email is None and self.phone is None:
            raise ValueError("Email or phone must be provided.")
        return self


class ContactPersonalDataResponse(BaseModel):
    name: str
    email: EmailStr | None
    phone: str | None


class ContactResponse(BaseModel):
    id: UUID
    status: ContactStatus
    created_at: datetime
    updated_at: datetime
    deactivated_at: datetime | None
    personal_data: ContactPersonalDataResponse | None


class ContactPageResponse(BaseModel):
    items: list[ContactResponse]
    next_cursor: str | None


class ContactSearchResponse(BaseModel):
    items: list[ContactResponse]
