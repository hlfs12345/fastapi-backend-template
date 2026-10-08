from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.legal import ApplicationPlatform, LegalAcceptanceScope


class LegalPublicationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=1_000_000)
    acceptance_scope: LegalAcceptanceScope
    is_required: bool


class LegalDocumentCreateRequest(LegalPublicationRequest):
    key: str = Field(
        min_length=1,
        max_length=63,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )


class LegalVersionResponse(BaseModel):
    document_id: UUID
    document_key: str
    version_id: UUID
    version: int
    title: str
    content: str
    acceptance_scope: LegalAcceptanceScope
    is_required: bool
    published_at: datetime


class LegalAcceptanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_platform: ApplicationPlatform
    application_version: str = Field(min_length=1, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LegalAcceptanceResponse(BaseModel):
    id: UUID
    legal_document_version_id: UUID
    acceptance_scope: LegalAcceptanceScope
    accepted_at: datetime
    application_platform: ApplicationPlatform
    application_version: str
    actor_roles: list[dict[str, Any]]
    metadata: dict[str, Any]
