from ipaddress import ip_address
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.api.dependencies import get_legal_service, get_tenant_context, require_permission
from app.core.permissions import LEGAL_PUBLISH
from app.core.tenant_context import TenantContext
from app.schemas.legal import (
    LegalAcceptanceRequest,
    LegalAcceptanceResponse,
    LegalDocumentCreateRequest,
    LegalPublicationRequest,
    LegalVersionResponse,
)
from app.services.legal import LegalAcceptanceDetails, LegalService, LegalVersionDetails

router = APIRouter(prefix="/legal", tags=["legal"])
require_legal_publish = require_permission(LEGAL_PUBLISH)


@router.get("/pending", response_model=list[LegalVersionResponse])
async def list_pending_versions(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[LegalService, Depends(get_legal_service)],
) -> list[LegalVersionResponse]:
    return [_version_response(item) for item in await service.list_pending_versions(context)]


@router.get("/documents/current", response_model=list[LegalVersionResponse])
async def list_current_versions(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[LegalService, Depends(get_legal_service)],
) -> list[LegalVersionResponse]:
    return [_version_response(item) for item in await service.list_current_versions(context)]


@router.get(
    "/document-versions/{version_id}",
    response_model=LegalVersionResponse,
)
async def get_legal_version(
    version_id: UUID,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[LegalService, Depends(get_legal_service)],
) -> LegalVersionResponse:
    version = await service.get_visible_version(context=context, version_id=version_id)
    return _version_response(version)


@router.put(
    "/document-versions/{version_id}/acceptance",
    response_model=LegalAcceptanceResponse,
)
async def accept_legal_version(
    version_id: UUID,
    payload: LegalAcceptanceRequest,
    request: Request,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[LegalService, Depends(get_legal_service)],
) -> LegalAcceptanceResponse:
    acceptance = await service.accept_version(
        context=context,
        version_id=version_id,
        application_platform=payload.application_platform,
        application_version=payload.application_version.strip(),
        metadata=payload.metadata,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
    )
    return _acceptance_response(acceptance)


@router.post(
    "/documents",
    response_model=LegalVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_legal_document(
    payload: LegalDocumentCreateRequest,
    context: Annotated[TenantContext, Depends(require_legal_publish)],
    service: Annotated[LegalService, Depends(get_legal_service)],
) -> LegalVersionResponse:
    version = await service.create_document(
        context=context,
        key=payload.key,
        title=payload.title,
        content=payload.content,
        acceptance_scope=payload.acceptance_scope,
        is_required=payload.is_required,
    )
    return _version_response(version)


@router.post(
    "/documents/{document_id}/versions",
    response_model=LegalVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def publish_legal_version(
    document_id: UUID,
    payload: LegalPublicationRequest,
    context: Annotated[TenantContext, Depends(require_legal_publish)],
    service: Annotated[LegalService, Depends(get_legal_service)],
) -> LegalVersionResponse:
    version = await service.publish_version(
        context=context,
        document_id=document_id,
        title=payload.title,
        content=payload.content,
        acceptance_scope=payload.acceptance_scope,
        is_required=payload.is_required,
    )
    return _version_response(version)


def _client_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    try:
        return str(ip_address(request.client.host))
    except ValueError:
        return None


def _version_response(version: LegalVersionDetails) -> LegalVersionResponse:
    return LegalVersionResponse(
        document_id=version.document_id,
        document_key=version.document_key,
        version_id=version.version_id,
        version=version.version,
        title=version.title,
        content=version.content,
        acceptance_scope=version.acceptance_scope,
        is_required=version.is_required,
        published_at=version.published_at,
    )


def _acceptance_response(acceptance: LegalAcceptanceDetails) -> LegalAcceptanceResponse:
    return LegalAcceptanceResponse(
        id=acceptance.id,
        legal_document_version_id=acceptance.legal_document_version_id,
        acceptance_scope=acceptance.acceptance_scope,
        accepted_at=acceptance.accepted_at,
        application_platform=acceptance.application_platform,
        application_version=acceptance.application_version,
        actor_roles=list(acceptance.actor_roles),
        metadata=acceptance.metadata,
    )
