from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_tenant_service, require_permission
from app.core.permissions import TENANT_MANAGE, TENANT_VIEW
from app.core.tenant_context import TenantContext
from app.schemas.tenants import TenantResponse, TenantUpdateRequest
from app.services.tenants import TenantDetails, TenantService

router = APIRouter(prefix="/tenant", tags=["tenant"])
require_tenant_view = require_permission(TENANT_VIEW)
require_tenant_manage = require_permission(TENANT_MANAGE)


@router.get("", response_model=TenantResponse)
async def get_tenant(
    context: Annotated[TenantContext, Depends(require_tenant_view)],
    service: Annotated[TenantService, Depends(get_tenant_service)],
) -> TenantResponse:
    return _tenant_response(await service.get_tenant(context))


@router.patch("", response_model=TenantResponse)
async def update_tenant(
    payload: TenantUpdateRequest,
    context: Annotated[TenantContext, Depends(require_tenant_manage)],
    service: Annotated[TenantService, Depends(get_tenant_service)],
) -> TenantResponse:
    tenant = await service.update_tenant(context=context, name=payload.name)
    return _tenant_response(tenant)


def _tenant_response(tenant: TenantDetails) -> TenantResponse:
    return TenantResponse(name=tenant.name, slug=tenant.slug)
