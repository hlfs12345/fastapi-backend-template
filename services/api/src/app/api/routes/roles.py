from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import get_role_service, require_permission
from app.core.permissions import ROLES_MANAGE, ROLES_VIEW
from app.core.tenant_context import TenantContext
from app.schemas.roles import (
    PermissionResponse,
    RoleCreateRequest,
    RoleResponse,
    RoleUpdateRequest,
)
from app.services.roles import RoleDetails, RoleService

router = APIRouter(prefix="/roles", tags=["roles"])
require_roles_view = require_permission(ROLES_VIEW)
require_roles_manage = require_permission(ROLES_MANAGE)


@router.get("/permissions", response_model=list[PermissionResponse])
async def list_permissions(
    context: Annotated[TenantContext, Depends(require_roles_view)],
    service: Annotated[RoleService, Depends(get_role_service)],
) -> list[PermissionResponse]:
    del context
    return [
        PermissionResponse(code=permission.code, description=permission.description)
        for permission in await service.list_permissions()
    ]


@router.get("", response_model=list[RoleResponse])
async def list_roles(
    context: Annotated[TenantContext, Depends(require_roles_view)],
    service: Annotated[RoleService, Depends(get_role_service)],
) -> list[RoleResponse]:
    return [_role_response(role) for role in await service.list_roles(context)]


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: RoleCreateRequest,
    context: Annotated[TenantContext, Depends(require_roles_manage)],
    service: Annotated[RoleService, Depends(get_role_service)],
) -> RoleResponse:
    role = await service.create_role(
        context=context,
        key=payload.key,
        name=payload.name,
        description=payload.description,
        permission_codes=frozenset(payload.permission_codes),
    )
    return _role_response(role)


@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: UUID,
    payload: RoleUpdateRequest,
    context: Annotated[TenantContext, Depends(require_roles_manage)],
    service: Annotated[RoleService, Depends(get_role_service)],
) -> RoleResponse:
    role = await service.update_role(
        context=context,
        role_id=role_id,
        name=payload.name,
        description=payload.description,
        permission_codes=frozenset(payload.permission_codes),
    )
    return _role_response(role)


@router.post(
    "/{role_id}/members/{tenant_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def assign_role(
    role_id: UUID,
    tenant_user_id: UUID,
    context: Annotated[TenantContext, Depends(require_roles_manage)],
    service: Annotated[RoleService, Depends(get_role_service)],
) -> Response:
    await service.assign_role(
        context=context,
        role_id=role_id,
        tenant_user_id=tenant_user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{role_id}/members/{tenant_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unassign_role(
    role_id: UUID,
    tenant_user_id: UUID,
    context: Annotated[TenantContext, Depends(require_roles_manage)],
    service: Annotated[RoleService, Depends(get_role_service)],
) -> Response:
    await service.unassign_role(
        context=context,
        role_id=role_id,
        tenant_user_id=tenant_user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _role_response(role: RoleDetails) -> RoleResponse:
    return RoleResponse(
        id=role.id,
        tenant_id=role.tenant_id,
        key=role.key,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        permission_codes=list(role.permission_codes),
    )
