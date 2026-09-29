from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from app.models import Role, RolePermission, Tenant, TenantUser, TenantUserRole, User


class ProvisioningRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def transaction(self) -> AsyncSessionTransaction:
        return self._session.begin()

    async def get_tenant_by_slug(self, slug: str) -> Tenant | None:
        statement = select(Tenant).where(Tenant.slug == slug)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_user_by_email_blind_index_for_update(
        self,
        email_blind_index: str,
    ) -> User | None:
        statement = (
            select(User).where(User.email_blind_index == email_blind_index).with_for_update(of=User)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    def add_tenant(self, tenant: Tenant) -> None:
        self._session.add(tenant)

    def add_user(self, user: User) -> None:
        self._session.add(user)

    def add_membership(self, membership: TenantUser) -> None:
        self._session.add(membership)

    def add_role(self, role: Role) -> None:
        self._session.add(role)

    def add_role_permission(self, role_permission: RolePermission) -> None:
        self._session.add(role_permission)

    def add_tenant_user_role(self, tenant_user_role: TenantUserRole) -> None:
        self._session.add(tenant_user_role)

    async def flush(self) -> None:
        await self._session.flush()
