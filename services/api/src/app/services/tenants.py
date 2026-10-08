from dataclasses import dataclass

from app.core.errors import ApplicationError
from app.core.tenant_context import TenantContext
from app.models import Tenant
from app.repositories.tenants import TenantRepository


@dataclass(frozen=True, slots=True)
class TenantDetails:
    name: str
    slug: str


class TenantService:
    def __init__(self, repository: TenantRepository) -> None:
        self._repository = repository

    async def get_tenant(self, context: TenantContext) -> TenantDetails:
        tenant = await self._repository.get_active_tenant(context.tenant_id)
        if tenant is None:
            raise _tenant_not_found()
        return _tenant_details(tenant)

    async def update_tenant(
        self,
        *,
        context: TenantContext,
        name: str,
    ) -> TenantDetails:
        normalized_name = name.strip()
        if not normalized_name or len(normalized_name) > 200:
            raise ApplicationError(
                code="invalid_tenant",
                message="The tenant data is invalid.",
                status_code=422,
            )

        async with self._repository.transaction():
            tenant = await self._repository.get_active_tenant_for_update(context.tenant_id)
            if tenant is None:
                raise _tenant_not_found()
            tenant.name = normalized_name
            await self._repository.flush()
        return _tenant_details(tenant)


def _tenant_details(tenant: Tenant) -> TenantDetails:
    return TenantDetails(name=tenant.name, slug=tenant.slug)


def _tenant_not_found() -> ApplicationError:
    return ApplicationError(
        code="tenant_not_found",
        message="The tenant was not found.",
        status_code=404,
    )
