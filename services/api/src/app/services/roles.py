import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.core.errors import ApplicationError
from app.core.permissions import ALL_PERMISSION_CODES
from app.core.tenant_context import TenantContext
from app.models import Role, TenantUserRole
from app.repositories.roles import RoleRepository

_ROLE_KEY_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class PermissionDetails:
    code: str
    description: str


@dataclass(frozen=True, slots=True)
class RoleDetails:
    id: UUID
    tenant_id: UUID
    key: str
    name: str
    description: str | None
    is_system: bool
    permission_codes: tuple[str, ...]


class RoleService:
    def __init__(self, repository: RoleRepository) -> None:
        self._repository = repository

    async def list_permissions(self) -> list[PermissionDetails]:
        permissions = await self._repository.list_permissions()
        return [
            PermissionDetails(code=permission.code, description=permission.description)
            for permission in permissions
        ]

    async def list_roles(self, context: TenantContext) -> list[RoleDetails]:
        roles = await self._repository.list_roles(context.tenant_id)
        permission_codes = await self._repository.get_permission_codes_for_roles(
            tenant_id=context.tenant_id,
            role_ids=[role.id for role in roles],
        )
        return [_role_details(role, permission_codes.get(role.id, frozenset())) for role in roles]

    async def create_role(
        self,
        *,
        context: TenantContext,
        key: str,
        name: str,
        description: str | None,
        permission_codes: frozenset[str],
    ) -> RoleDetails:
        normalized_name, normalized_description = _validate_role_input(
            key=key,
            name=name,
            description=description,
            permission_codes=permission_codes,
        )
        role = Role(
            id=uuid4(),
            tenant_id=context.tenant_id,
            key=key,
            name=normalized_name,
            description=normalized_description,
            is_system=False,
        )
        try:
            async with self._repository.transaction():
                if (
                    await self._repository.get_role_by_key(
                        tenant_id=context.tenant_id,
                        key=key,
                    )
                    is not None
                ):
                    raise _role_key_conflict()
                self._repository.add_role(role)
                await self._repository.replace_permissions(
                    tenant_id=context.tenant_id,
                    role_id=role.id,
                    permission_codes=permission_codes,
                )
                await self._repository.flush()
        except IntegrityError as error:
            raise _role_key_conflict() from error
        return _role_details(role, permission_codes)

    async def update_role(
        self,
        *,
        context: TenantContext,
        role_id: UUID,
        name: str,
        description: str | None,
        permission_codes: frozenset[str],
    ) -> RoleDetails:
        normalized_name, normalized_description = _validate_role_input(
            key="custom",
            name=name,
            description=description,
            permission_codes=permission_codes,
        )
        async with self._repository.transaction():
            role = await self._repository.get_role_for_update(
                tenant_id=context.tenant_id,
                role_id=role_id,
            )
            if role is None:
                raise _role_not_found()
            if role.is_system:
                raise ApplicationError(
                    code="system_role_immutable",
                    message="System roles cannot be changed.",
                    status_code=409,
                )
            role.name = normalized_name
            role.description = normalized_description
            await self._repository.replace_permissions(
                tenant_id=context.tenant_id,
                role_id=role.id,
                permission_codes=permission_codes,
            )
            await self._repository.flush()
        return _role_details(role, permission_codes)

    async def assign_role(
        self,
        *,
        context: TenantContext,
        role_id: UUID,
        tenant_user_id: UUID,
    ) -> None:
        try:
            async with self._repository.transaction():
                role = await self._repository.get_role(
                    tenant_id=context.tenant_id,
                    role_id=role_id,
                )
                if role is None:
                    raise _role_not_found()
                member = await self._repository.get_active_tenant_user(
                    tenant_id=context.tenant_id,
                    tenant_user_id=tenant_user_id,
                )
                if member is None:
                    raise _tenant_user_not_found()
                if await self._repository.assignment_exists(
                    tenant_id=context.tenant_id,
                    tenant_user_id=tenant_user_id,
                    role_id=role_id,
                ):
                    return
                self._repository.add_assignment(
                    TenantUserRole(
                        tenant_id=context.tenant_id,
                        tenant_user_id=tenant_user_id,
                        role_id=role_id,
                        assigned_by_tenant_user_id=context.tenant_user_id,
                    )
                )
                await self._repository.flush()
        except IntegrityError as error:
            raise ApplicationError(
                code="role_assignment_conflict",
                message="The role assignment could not be created.",
                status_code=409,
            ) from error

    async def unassign_role(
        self,
        *,
        context: TenantContext,
        role_id: UUID,
        tenant_user_id: UUID,
    ) -> None:
        async with self._repository.transaction():
            role = await self._repository.get_role_for_update(
                tenant_id=context.tenant_id,
                role_id=role_id,
            )
            if role is None:
                raise _role_not_found()
            if not await self._repository.assignment_exists(
                tenant_id=context.tenant_id,
                tenant_user_id=tenant_user_id,
                role_id=role_id,
            ):
                return
            if (
                role.is_system
                and await self._repository.count_role_assignments(
                    tenant_id=context.tenant_id,
                    role_id=role_id,
                )
                <= 1
            ):
                raise ApplicationError(
                    code="last_system_role_assignment",
                    message="The last assignment of a system role cannot be removed.",
                    status_code=409,
                )
            await self._repository.remove_assignment(
                tenant_id=context.tenant_id,
                tenant_user_id=tenant_user_id,
                role_id=role_id,
            )


def _validate_role_input(
    *,
    key: str,
    name: str,
    description: str | None,
    permission_codes: frozenset[str],
) -> tuple[str, str | None]:
    normalized_name = name.strip()
    normalized_description = description.strip() if description is not None else None
    if not _ROLE_KEY_PATTERN.fullmatch(key) or not 1 <= len(key) <= 63:
        raise _invalid_role()
    if not normalized_name or len(normalized_name) > 100:
        raise _invalid_role()
    if normalized_description == "":
        normalized_description = None
    if normalized_description is not None and len(normalized_description) > 500:
        raise _invalid_role()
    if not permission_codes <= ALL_PERMISSION_CODES:
        raise ApplicationError(
            code="unknown_permission",
            message="One or more permissions do not exist.",
            status_code=422,
        )
    return normalized_name, normalized_description


def _role_details(role: Role, permission_codes: frozenset[str]) -> RoleDetails:
    return RoleDetails(
        id=role.id,
        tenant_id=role.tenant_id,
        key=role.key,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        permission_codes=tuple(sorted(permission_codes)),
    )


def _invalid_role() -> ApplicationError:
    return ApplicationError(
        code="invalid_role",
        message="The role data is invalid.",
        status_code=422,
    )


def _role_key_conflict() -> ApplicationError:
    return ApplicationError(
        code="role_key_conflict",
        message="A role with this key already exists in the tenant.",
        status_code=409,
    )


def _role_not_found() -> ApplicationError:
    return ApplicationError(
        code="role_not_found",
        message="The role was not found.",
        status_code=404,
    )


def _tenant_user_not_found() -> ApplicationError:
    return ApplicationError(
        code="tenant_user_not_found",
        message="The tenant user was not found.",
        status_code=404,
    )
