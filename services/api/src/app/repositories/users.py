from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Select, and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from app.models import Role, TenantUser, TenantUserRole, User


@dataclass(frozen=True, slots=True)
class TenantMember:
    tenant_user: TenantUser
    user: User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def transaction(self) -> AsyncSessionTransaction:
        return self._session.begin()

    async def list_members(self, tenant_id: UUID) -> list[TenantMember]:
        statement = (
            self._member_statement()
            .where(TenantUser.tenant_id == tenant_id)
            .order_by(TenantUser.joined_at, TenantUser.id)
        )
        return [TenantMember(*row) for row in (await self._session.execute(statement)).all()]

    async def get_member(
        self,
        *,
        tenant_id: UUID,
        tenant_user_id: UUID,
    ) -> TenantMember | None:
        statement = self._member_statement().where(
            TenantUser.tenant_id == tenant_id,
            TenantUser.id == tenant_user_id,
        )
        row = (await self._session.execute(statement)).one_or_none()
        return TenantMember(*row) if row else None

    async def get_member_for_update(
        self,
        *,
        tenant_id: UUID,
        tenant_user_id: UUID,
    ) -> TenantMember | None:
        statement = (
            self._member_statement()
            .where(
                TenantUser.tenant_id == tenant_id,
                TenantUser.id == tenant_user_id,
            )
            .with_for_update(of=TenantUser)
        )
        row = (await self._session.execute(statement)).one_or_none()
        return TenantMember(*row) if row else None

    async def get_roles_for_members(
        self,
        *,
        tenant_id: UUID,
        tenant_user_ids: list[UUID],
    ) -> dict[UUID, list[Role]]:
        if not tenant_user_ids:
            return {}
        statement = (
            select(TenantUserRole.tenant_user_id, Role)
            .join(
                Role,
                and_(
                    Role.id == TenantUserRole.role_id,
                    Role.tenant_id == TenantUserRole.tenant_id,
                ),
            )
            .where(
                TenantUserRole.tenant_id == tenant_id,
                TenantUserRole.tenant_user_id.in_(tenant_user_ids),
                Role.deactivated_at.is_(None),
            )
            .order_by(Role.name, Role.key, Role.id)
        )
        grouped = {tenant_user_id: [] for tenant_user_id in tenant_user_ids}
        for tenant_user_id, role in (await self._session.execute(statement)).all():
            grouped[tenant_user_id].append(role)
        return grouped

    async def get_active_roles(
        self,
        *,
        tenant_id: UUID,
        role_ids: frozenset[UUID],
    ) -> list[Role]:
        if not role_ids:
            return []
        statement = (
            select(Role)
            .where(
                Role.tenant_id == tenant_id,
                Role.id.in_(role_ids),
                Role.deactivated_at.is_(None),
            )
            .order_by(Role.name, Role.key, Role.id)
        )
        return list((await self._session.execute(statement)).scalars())

    async def get_owner_role_for_update(self, tenant_id: UUID) -> Role | None:
        statement = (
            select(Role)
            .where(
                Role.tenant_id == tenant_id,
                Role.key == "owner",
                Role.is_system.is_(True),
            )
            .with_for_update(of=Role)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def member_has_role(
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

    async def count_active_role_members(self, *, tenant_id: UUID, role_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(TenantUserRole)
            .join(
                TenantUser,
                and_(
                    TenantUser.id == TenantUserRole.tenant_user_id,
                    TenantUser.tenant_id == TenantUserRole.tenant_id,
                ),
            )
            .where(
                TenantUserRole.tenant_id == tenant_id,
                TenantUserRole.role_id == role_id,
                TenantUser.deactivated_at.is_(None),
            )
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def synchronize_role_assignments(
        self,
        *,
        tenant_id: UUID,
        tenant_user_id: UUID,
        role_ids: frozenset[UUID],
        assigned_by_tenant_user_id: UUID,
    ) -> None:
        current_statement = select(TenantUserRole.role_id).where(
            TenantUserRole.tenant_id == tenant_id,
            TenantUserRole.tenant_user_id == tenant_user_id,
        )
        current_role_ids = frozenset((await self._session.execute(current_statement)).scalars())
        removed_role_ids = current_role_ids - role_ids
        added_role_ids = role_ids - current_role_ids
        if removed_role_ids:
            await self._session.execute(
                delete(TenantUserRole).where(
                    TenantUserRole.tenant_id == tenant_id,
                    TenantUserRole.tenant_user_id == tenant_user_id,
                    TenantUserRole.role_id.in_(removed_role_ids),
                )
            )
        self._session.add_all(
            TenantUserRole(
                tenant_id=tenant_id,
                tenant_user_id=tenant_user_id,
                role_id=role_id,
                assigned_by_tenant_user_id=assigned_by_tenant_user_id,
            )
            for role_id in sorted(added_role_ids)
        )

    async def flush(self) -> None:
        await self._session.flush()

    @staticmethod
    def _member_statement() -> Select[tuple[TenantUser, User]]:
        return select(TenantUser, User).join(User, User.id == TenantUser.user_id)
