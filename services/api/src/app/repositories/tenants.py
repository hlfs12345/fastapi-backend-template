from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from app.models import Tenant


class TenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def transaction(self) -> AsyncSessionTransaction:
        return self._session.begin()

    async def get_active_tenant(self, tenant_id: UUID) -> Tenant | None:
        statement = select(Tenant).where(
            Tenant.id == tenant_id,
            Tenant.deactivated_at.is_(None),
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_active_tenant_for_update(self, tenant_id: UUID) -> Tenant | None:
        statement = (
            select(Tenant)
            .where(
                Tenant.id == tenant_id,
                Tenant.deactivated_at.is_(None),
            )
            .with_for_update(of=Tenant)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def flush(self) -> None:
        await self._session.flush()
