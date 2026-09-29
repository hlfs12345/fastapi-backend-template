from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest

from app.api.dependencies import require_permission
from app.core.errors import ApplicationError
from app.core.permissions import ROLES_MANAGE, ROLES_VIEW
from app.core.tenant_context import TenantContext
from app.models import Permission, Role, TenantUser, TenantUserRole
from app.services.roles import RoleService


class FakeRoleRepository:
    def __init__(self) -> None:
        self.permissions = [
            Permission(code=ROLES_VIEW, description="View roles."),
            Permission(code=ROLES_MANAGE, description="Manage roles."),
        ]
        self.roles: list[Role] = []
        self.role_permissions: dict[UUID, frozenset[str]] = {}
        self.members: list[TenantUser] = []
        self.assignments: set[tuple[UUID, UUID, UUID]] = set()

    @asynccontextmanager
    async def transaction(self):
        yield

    async def list_permissions(self) -> list[Permission]:
        return self.permissions

    async def list_roles(self, tenant_id: UUID) -> list[Role]:
        return [
            role
            for role in self.roles
            if role.tenant_id == tenant_id and role.deactivated_at is None
        ]

    async def get_role(self, *, tenant_id: UUID, role_id: UUID) -> Role | None:
        return next(
            (
                role
                for role in self.roles
                if role.tenant_id == tenant_id
                and role.id == role_id
                and role.deactivated_at is None
            ),
            None,
        )

    async def get_role_for_update(self, *, tenant_id: UUID, role_id: UUID) -> Role | None:
        return await self.get_role(tenant_id=tenant_id, role_id=role_id)

    async def get_role_by_key(self, *, tenant_id: UUID, key: str) -> Role | None:
        return next(
            (role for role in self.roles if role.tenant_id == tenant_id and role.key == key),
            None,
        )

    async def get_permission_codes_for_roles(
        self,
        *,
        tenant_id: UUID,
        role_ids: list[UUID],
    ) -> dict[UUID, frozenset[str]]:
        scoped_role_ids = {
            role.id for role in self.roles if role.tenant_id == tenant_id and role.id in role_ids
        }
        return {
            role_id: self.role_permissions.get(role_id, frozenset()) for role_id in scoped_role_ids
        }

    async def get_active_tenant_user(
        self,
        *,
        tenant_id: UUID,
        tenant_user_id: UUID,
    ) -> TenantUser | None:
        return next(
            (
                member
                for member in self.members
                if member.tenant_id == tenant_id
                and member.id == tenant_user_id
                and member.deactivated_at is None
            ),
            None,
        )

    async def assignment_exists(
        self,
        *,
        tenant_id: UUID,
        tenant_user_id: UUID,
        role_id: UUID,
    ) -> bool:
        return (tenant_id, tenant_user_id, role_id) in self.assignments

    async def count_role_assignments(self, *, tenant_id: UUID, role_id: UUID) -> int:
        return sum(
            assignment_tenant_id == tenant_id and assignment_role_id == role_id
            for assignment_tenant_id, _, assignment_role_id in self.assignments
        )

    def add_role(self, role: Role) -> None:
        self.roles.append(role)

    def add_assignment(self, assignment: TenantUserRole) -> None:
        self.assignments.add((assignment.tenant_id, assignment.tenant_user_id, assignment.role_id))

    async def replace_permissions(
        self,
        *,
        tenant_id: UUID,
        role_id: UUID,
        permission_codes: frozenset[str],
    ) -> None:
        assert any(role.id == role_id and role.tenant_id == tenant_id for role in self.roles)
        self.role_permissions[role_id] = permission_codes

    async def remove_assignment(
        self,
        *,
        tenant_id: UUID,
        tenant_user_id: UUID,
        role_id: UUID,
    ) -> None:
        self.assignments.remove((tenant_id, tenant_user_id, role_id))

    async def flush(self) -> None:
        return None


def _context(*, tenant_id: UUID | None = None, permissions: frozenset[str] = frozenset()):
    return TenantContext(
        tenant_id=tenant_id or uuid4(),
        user_id=uuid4(),
        tenant_user_id=uuid4(),
        permissions=permissions,
    )


@pytest.mark.asyncio
async def test_permission_dependency_allows_only_semantic_permission() -> None:
    allowed = _context(permissions=frozenset({ROLES_VIEW}))
    denied = _context(permissions=frozenset())
    dependency = require_permission(ROLES_VIEW)

    assert await dependency(allowed) is allowed
    with pytest.raises(ApplicationError) as raised:
        await dependency(denied)

    assert raised.value.code == "permission_denied"
    assert raised.value.status_code == 403


@pytest.mark.asyncio
async def test_roles_are_created_and_listed_only_in_current_tenant() -> None:
    repository = FakeRoleRepository()
    service = RoleService(repository)  # type: ignore[arg-type]
    first_context = _context()
    other_context = _context()

    created = await service.create_role(
        context=first_context,
        key="sales-manager",
        name=" Sales manager ",
        description=" Manages sales ",
        permission_codes=frozenset({ROLES_VIEW}),
    )

    assert created.tenant_id == first_context.tenant_id
    assert created.name == "Sales manager"
    assert created.description == "Manages sales"
    assert created.permission_codes == (ROLES_VIEW,)
    assert [role.id for role in await service.list_roles(first_context)] == [created.id]
    assert await service.list_roles(other_context) == []


@pytest.mark.asyncio
async def test_role_assignment_rejects_member_from_another_tenant() -> None:
    repository = FakeRoleRepository()
    service = RoleService(repository)  # type: ignore[arg-type]
    context = _context()
    role = Role(
        id=uuid4(),
        tenant_id=context.tenant_id,
        key="operator",
        name="Operator",
        is_system=False,
    )
    foreign_member = TenantUser(
        id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
    )
    repository.roles.append(role)
    repository.members.append(foreign_member)

    with pytest.raises(ApplicationError) as raised:
        await service.assign_role(
            context=context,
            role_id=role.id,
            tenant_user_id=foreign_member.id,
        )

    assert raised.value.code == "tenant_user_not_found"
    assert not repository.assignments


@pytest.mark.asyncio
async def test_system_role_is_immutable_and_keeps_at_least_one_assignment() -> None:
    repository = FakeRoleRepository()
    service = RoleService(repository)  # type: ignore[arg-type]
    context = _context()
    owner = Role(
        id=uuid4(),
        tenant_id=context.tenant_id,
        key="owner",
        name="Owner",
        is_system=True,
    )
    repository.roles.append(owner)
    repository.assignments.add((context.tenant_id, context.tenant_user_id, owner.id))

    with pytest.raises(ApplicationError) as update_error:
        await service.update_role(
            context=context,
            role_id=owner.id,
            name="Changed",
            description=None,
            permission_codes=frozenset(),
        )
    with pytest.raises(ApplicationError) as unassign_error:
        await service.unassign_role(
            context=context,
            role_id=owner.id,
            tenant_user_id=context.tenant_user_id,
        )

    assert update_error.value.code == "system_role_immutable"
    assert unassign_error.value.code == "last_system_role_assignment"
    assert (context.tenant_id, context.tenant_user_id, owner.id) in repository.assignments


@pytest.mark.asyncio
async def test_role_rejects_unknown_permission() -> None:
    repository = FakeRoleRepository()
    service = RoleService(repository)  # type: ignore[arg-type]

    with pytest.raises(ApplicationError) as raised:
        await service.create_role(
            context=_context(),
            key="invalid",
            name="Invalid",
            description=None,
            permission_codes=frozenset({"unknown.permission"}),
        )

    assert raised.value.code == "unknown_permission"
    assert not repository.roles
