from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.dependencies import get_contact_service, require_permission
from app.core.errors import ApplicationError
from app.core.permissions import CONTACTS_EDIT, CONTACTS_VIEW, CONTACTS_VIEW_SENSITIVE
from app.core.tenant_context import TenantContext
from app.schemas.contacts import (
    ContactCreateRequest,
    ContactPageResponse,
    ContactPersonalDataResponse,
    ContactResponse,
    ContactSearchRequest,
    ContactSearchResponse,
    ContactStatusFilter,
    ContactUpdateRequest,
)
from app.services.contacts import ContactDetails, ContactService

router = APIRouter(prefix="/contacts", tags=["contacts"])
require_contacts_view = require_permission(CONTACTS_VIEW)
require_contacts_edit = require_permission(CONTACTS_EDIT)


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    payload: ContactCreateRequest,
    response: Response,
    context: Annotated[TenantContext, Depends(require_contacts_edit)],
    service: Annotated[ContactService, Depends(get_contact_service)],
) -> ContactResponse:
    _require_sensitive(context)
    contact = await service.create_contact(
        context=context,
        name=payload.name,
        email=str(payload.email) if payload.email is not None else None,
        phone=payload.phone,
    )
    _prevent_caching(response)
    return _contact_response(contact)


@router.get("", response_model=ContactPageResponse)
async def list_contacts(
    response: Response,
    context: Annotated[TenantContext, Depends(require_contacts_view)],
    service: Annotated[ContactService, Depends(get_contact_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    status_filter: Annotated[
        ContactStatusFilter,
        Query(alias="status"),
    ] = ContactStatusFilter.ACTIVE,
    include_sensitive: bool = False,
) -> ContactPageResponse:
    if include_sensitive:
        _require_sensitive(context)
    page = await service.list_contacts(
        context=context,
        status=status_filter.value,
        limit=limit,
        cursor=cursor,
        include_sensitive=include_sensitive,
    )
    _prevent_caching(response)
    return ContactPageResponse(
        items=[_contact_response(contact) for contact in page.items],
        next_cursor=page.next_cursor,
    )


@router.post("/search", response_model=ContactSearchResponse)
async def search_contacts(
    payload: ContactSearchRequest,
    response: Response,
    context: Annotated[TenantContext, Depends(require_contacts_view)],
    service: Annotated[ContactService, Depends(get_contact_service)],
) -> ContactSearchResponse:
    _require_sensitive(context)
    contacts = await service.search_contacts(
        context=context,
        email=str(payload.email) if payload.email is not None else None,
        phone=payload.phone,
        include_deactivated=payload.include_deactivated,
    )
    _prevent_caching(response)
    return ContactSearchResponse(items=[_contact_response(contact) for contact in contacts])


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: UUID,
    response: Response,
    context: Annotated[TenantContext, Depends(require_contacts_view)],
    service: Annotated[ContactService, Depends(get_contact_service)],
    include_sensitive: bool = False,
) -> ContactResponse:
    if include_sensitive:
        _require_sensitive(context)
    contact = await service.get_contact(
        context=context,
        contact_id=contact_id,
        include_sensitive=include_sensitive,
    )
    _prevent_caching(response)
    return _contact_response(contact)


@router.patch("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: UUID,
    payload: ContactUpdateRequest,
    response: Response,
    context: Annotated[TenantContext, Depends(require_contacts_edit)],
    service: Annotated[ContactService, Depends(get_contact_service)],
) -> ContactResponse:
    _require_sensitive(context)
    contact = await service.update_contact(
        context=context,
        contact_id=contact_id,
        fields=frozenset(payload.model_fields_set),
        name=payload.name,
        email=str(payload.email) if payload.email is not None else None,
        phone=payload.phone,
    )
    _prevent_caching(response)
    return _contact_response(contact)


@router.post("/{contact_id}/deactivate", response_model=ContactResponse)
async def deactivate_contact(
    contact_id: UUID,
    response: Response,
    context: Annotated[TenantContext, Depends(require_contacts_edit)],
    service: Annotated[ContactService, Depends(get_contact_service)],
) -> ContactResponse:
    contact = await service.deactivate_contact(context=context, contact_id=contact_id)
    _prevent_caching(response)
    return _contact_response(contact)


def _require_sensitive(context: TenantContext) -> None:
    if CONTACTS_VIEW_SENSITIVE not in context.permissions:
        raise ApplicationError(
            code="permission_denied",
            message="Permission denied.",
            status_code=403,
        )


def _contact_response(contact: ContactDetails) -> ContactResponse:
    personal_data = contact.personal_data
    return ContactResponse(
        id=contact.id,
        status=contact.status,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
        deactivated_at=contact.deactivated_at,
        personal_data=(
            ContactPersonalDataResponse(
                name=personal_data.name,
                email=personal_data.email,
                phone=personal_data.phone,
            )
            if personal_data is not None
            else None
        ),
    )


def _prevent_caching(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
