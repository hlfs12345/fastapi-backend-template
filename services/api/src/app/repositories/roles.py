from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from app.models import Permission, Role, RolePermission, TenantUser, TenantUserRole


class RoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def transaction(self) -> AsyncSessionTransaction:
        return self._session.begin()

    async def list_permissions(self) -> list[Permission]:
        statement = select(Permission).order_by(Permission.code)
        return list((await self._session.execute(statement)).scalars())

    async def list_roles(self, tenant_id: UUID) -> list[Role]:
        statement = (
            select(Role)
            .where(Role.tenant_id == tenant_id, Role.deactivated_at.is_(None))
            .order_by(Role.name, Role.key)
        )
        return list((await self._session.execute(statement)).scalars())

    async def get_role(self, *, tenant_id: UUID, role_id: UUID) -> Role | None:
        statement = select(Role).where(
            Role.tenant_id == tenant_id,
            Role.id == role_id,
            Role.deactivated_at.is_(None),
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_role_for_update(self, *, tenant_id: UUID, role_id: UUID) -> Role | None:
        statement = (
            select(Role)
            .where(
                Role.tenant_id == tenant_id,
                Role.id == role_id,
                Role.deactivated_at.is_(None),
            )
            .with_for_update(of=Role)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_role_by_key(self, *, tenant_id: UUID, key: str) -> Role | None:
        statement = select(Role).where(
            Role.tenant_id == tenant_id,
            Role.key == key,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_permission_codes(
        self,
        *,
        tenant_id: UUID,
        role_id: UUID,
    ) -> frozenset[str]:
        statement = select(RolePermission.permission_code).where(
            RolePermission.tenant_id == tenant_id,
            RolePermission.role_id == role_id,
        )
        return frozenset((await self._session.execute(statement)).scalars())

    async def get_permission_codes_for_roles(
        self,
        *,
        tenant_id: UUID,
        role_ids: list[UUID],
    ) -> dict[UUID, frozenset[str]]:
        if not role_ids:
            return {}
        statement = select(
            RolePermission.role_id,
            RolePermission.permission_code,
        ).where(
            RolePermission.tenant_id == tenant_id,
            RolePermission.role_id.in_(role_ids),
        )
        grouped: dict[UUID, set[str]] = {role_id: set() for role_id in role_ids}
        for role_id, permission_code in (await self._session.execute(statement)).all():
            grouped[role_id].add(permission_code)
        return {role_id: frozenset(codes) for role_id, codes in grouped.items()}

    async def get_active_tenant_user(
        self,
        *,
        tenant_id: UUID,
        tenant_user_id: UUID,
    ) -> TenantUser | None:
        statement = select(TenantUser).where(
            TenantUser.tenant_id == tenant_id,
            TenantUser.id == tenant_user_id,
            TenantUser.deactivated_at.is_(None),
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def assignment_exists(
        self,
        *,
        tenant_id: UUID,
        tenant_user_id: UUID,
        role_id: UUID,
    ) -> bool:
        statement = select(TenantUserRole.tenant_user_id).where(
            TenantUserRole.tenant_id == tenant_id,
            TenantUserRole.tenant_user_id == tenant_user_id,
            TenantUserRole.role_id == role_id,
        )
        return (await self._session.execute(statement)).scalar_one_or_none() is not None

    async def count_role_assignments(self, *, tenant_id: UUID, role_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(TenantUserRole)
            .where(
                TenantUserRole.tenant_id == tenant_id,
                TenantUserRole.role_id == role_id,
            )
        )
        return int((await self._session.execute(statement)).scalar_one())

    def add_role(self, role: Role) -> None:
        self._session.add(role)

    def add_assignment(self, assignment: TenantUserRole) -> None:
        self._session.add(assignment)

    async def replace_permissions(
        self,
        *,
        tenant_id: UUID,
        role_id: UUID,
        permission_codes: frozenset[str],
    ) -> None:
        await self._session.execute(
            delete(RolePermission).where(
                RolePermission.tenant_id == tenant_id,
                RolePermission.role_id == role_id,
            )
        )
        self._session.add_all(
            RolePermission(
                tenant_id=tenant_id,
                role_id=role_id,
                permission_code=permission_code,
            )
            for permission_code in sorted(permission_codes)
        )

    async def remove_assignment(
        self,
        *,
        tenant_id: UUID,
        tenant_user_id: UUID,
        role_id: UUID,
    ) -> None:
        await self._session.execute(
            delete(TenantUserRole).where(
                TenantUserRole.tenant_id == tenant_id,
                TenantUserRole.tenant_user_id == tenant_user_id,
                TenantUserRole.role_id == role_id,
            )
        )

    async def flush(self) -> None:
        await self._session.flush()
