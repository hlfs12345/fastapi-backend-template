from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import get_user_service, require_permission
from app.core.permissions import USERS_MANAGE, USERS_VIEW
from app.core.tenant_context import TenantContext
from app.schemas.users import (
    TenantUserResponse,
    TenantUserRoleResponse,
    TenantUserUpdateRequest,
)
from app.services.users import TenantMemberDetails, UserService

router = APIRouter(prefix="/users", tags=["users"])
require_users_view = require_permission(USERS_VIEW)
require_users_manage = require_permission(USERS_MANAGE)


@router.get("", response_model=list[TenantUserResponse])
async def list_users(
    context: Annotated[TenantContext, Depends(require_users_view)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> list[TenantUserResponse]:
    return [_user_response(member) for member in await service.list_members(context)]


@router.get("/{tenant_user_id}", response_model=TenantUserResponse)
async def get_user(
    tenant_user_id: UUID,
    context: Annotated[TenantContext, Depends(require_users_view)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> TenantUserResponse:
    member = await service.get_member(context=context, tenant_user_id=tenant_user_id)
    return _user_response(member)


@router.patch("/{tenant_user_id}", response_model=TenantUserResponse)
async def update_user(
    tenant_user_id: UUID,
    payload: TenantUserUpdateRequest,
    context: Annotated[TenantContext, Depends(require_users_manage)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> TenantUserResponse:
    member = await service.update_member(
        context=context,
        tenant_user_id=tenant_user_id,
        role_ids=frozenset(payload.role_ids) if payload.role_ids is not None else None,
    )
    return _user_response(member)


@router.post("/{tenant_user_id}/deactivate", response_model=TenantUserResponse)
async def deactivate_user(
    tenant_user_id: UUID,
    context: Annotated[TenantContext, Depends(require_users_manage)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> TenantUserResponse:
    member = await service.deactivate_member(
        context=context,
        tenant_user_id=tenant_user_id,
    )
    return _user_response(member)


@router.post("/{tenant_user_id}/activate", response_model=TenantUserResponse)
async def activate_user(
    tenant_user_id: UUID,
    context: Annotated[TenantContext, Depends(require_users_manage)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> TenantUserResponse:
    member = await service.activate_member(
        context=context,
        tenant_user_id=tenant_user_id,
    )
    return _user_response(member)


def _user_response(member: TenantMemberDetails) -> TenantUserResponse:
    return TenantUserResponse(
        id=member.id,
        user_id=member.user_id,
        email=member.email,
        joined_at=member.joined_at,
        deactivated_at=member.deactivated_at,
        is_active=member.is_active,
        roles=[
            TenantUserRoleResponse(
                id=role.id,
                key=role.key,
                name=role.name,
                is_system=role.is_system,
            )
            for role in member.roles
        ],
    )
