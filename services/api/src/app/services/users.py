from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.errors import ApplicationError
from app.core.tenant_context import TenantContext
from app.integrations.openbao import OpenBaoError
from app.models import Role
from app.repositories.users import TenantMember, UserRepository
from app.services.email_identity import EmailIdentityProtector


@dataclass(frozen=True, slots=True)
class AssignedRoleDetails:
    id: UUID
    key: str
    name: str
    is_system: bool


@dataclass(frozen=True, slots=True)
class TenantMemberDetails:
    id: UUID
    user_id: UUID
    email: str
    joined_at: datetime
    deactivated_at: datetime | None
    roles: tuple[AssignedRoleDetails, ...]

    @property
    def is_active(self) -> bool:
        return self.deactivated_at is None


class UserService:
    def __init__(
        self,
        repository: UserRepository,
        email_protector: EmailIdentityProtector,
    ) -> None:
        self._repository = repository
        self._email_protector = email_protector

    async def list_members(self, context: TenantContext) -> list[TenantMemberDetails]:
        members = await self._repository.list_members(context.tenant_id)
        roles = await self._repository.get_roles_for_members(
            tenant_id=context.tenant_id,
            tenant_user_ids=[member.tenant_user.id for member in members],
        )
        return [
            await self._member_details(member, roles.get(member.tenant_user.id, []))
            for member in members
        ]

    async def get_member(
        self,
        *,
        context: TenantContext,
        tenant_user_id: UUID,
    ) -> TenantMemberDetails:
        member = await self._repository.get_member(
            tenant_id=context.tenant_id,
            tenant_user_id=tenant_user_id,
        )
        if member is None:
            raise _tenant_user_not_found()
        roles = await self._roles_for_member(context.tenant_id, tenant_user_id)
        return await self._member_details(member, roles)

    async def update_member(
        self,
        *,
        context: TenantContext,
        tenant_user_id: UUID,
        role_ids: frozenset[UUID] | None,
    ) -> TenantMemberDetails:
        try:
            async with self._repository.transaction():
                owner = await self._repository.get_owner_role_for_update(context.tenant_id)
                member = await self._repository.get_member_for_update(
                    tenant_id=context.tenant_id,
                    tenant_user_id=tenant_user_id,
                )
                if member is None:
                    raise _tenant_user_not_found()
                if role_ids is not None:
                    roles = await self._repository.get_active_roles(
                        tenant_id=context.tenant_id,
                        role_ids=role_ids,
                    )
                    if {role.id for role in roles} != set(role_ids):
                        raise ApplicationError(
                            code="invalid_role_assignment",
                            message="One or more roles do not exist in the tenant.",
                            status_code=422,
                        )
                    await self._ensure_owner_remains_active(
                        context=context,
                        member=member,
                        owner=owner,
                        proposed_role_ids=role_ids,
                    )
                    await self._repository.synchronize_role_assignments(
                        tenant_id=context.tenant_id,
                        tenant_user_id=tenant_user_id,
                        role_ids=role_ids,
                        assigned_by_tenant_user_id=context.tenant_user_id,
                    )
                    await self._repository.flush()
                else:
                    roles = await self._roles_for_member(context.tenant_id, tenant_user_id)
        except IntegrityError as error:
            raise ApplicationError(
                code="role_assignment_conflict",
                message="The role assignments could not be updated.",
                status_code=409,
            ) from error
        return await self._member_details(member, roles)

    async def deactivate_member(
        self,
        *,
        context: TenantContext,
        tenant_user_id: UUID,
    ) -> TenantMemberDetails:
        async with self._repository.transaction():
            owner = await self._repository.get_owner_role_for_update(context.tenant_id)
            member = await self._repository.get_member_for_update(
                tenant_id=context.tenant_id,
                tenant_user_id=tenant_user_id,
            )
            if member is None:
                raise _tenant_user_not_found()
            if member.tenant_user.deactivated_at is None:
                await self._ensure_owner_remains_active(
                    context=context,
                    member=member,
                    owner=owner,
                    proposed_role_ids=frozenset(),
                    deactivating=True,
                )
                member.tenant_user.deactivated_at = datetime.now(UTC)
                await self._repository.flush()
            roles = await self._roles_for_member(context.tenant_id, tenant_user_id)
        return await self._member_details(member, roles)

    async def activate_member(
        self,
        *,
        context: TenantContext,
        tenant_user_id: UUID,
    ) -> TenantMemberDetails:
        async with self._repository.transaction():
            member = await self._repository.get_member_for_update(
                tenant_id=context.tenant_id,
                tenant_user_id=tenant_user_id,
            )
            if member is None:
                raise _tenant_user_not_found()
            member.tenant_user.deactivated_at = None
            await self._repository.flush()
            roles = await self._roles_for_member(context.tenant_id, tenant_user_id)
        return await self._member_details(member, roles)

    async def _ensure_owner_remains_active(
        self,
        *,
        context: TenantContext,
        member: TenantMember,
        owner: Role | None,
        proposed_role_ids: frozenset[UUID],
        deactivating: bool = False,
    ) -> None:
        if owner is None or member.tenant_user.deactivated_at is not None:
            return
        has_owner = await self._repository.member_has_role(
            tenant_id=context.tenant_id,
            tenant_user_id=member.tenant_user.id,
            role_id=owner.id,
        )
        keeps_owner = not deactivating and owner.id in proposed_role_ids
        if not has_owner or keeps_owner:
            return
        active_owner_count = await self._repository.count_active_role_members(
            tenant_id=context.tenant_id,
            role_id=owner.id,
        )
        if active_owner_count <= 1:
            raise ApplicationError(
                code="last_active_owner",
                message="The last active owner cannot be removed or deactivated.",
                status_code=409,
            )

    async def _roles_for_member(self, tenant_id: UUID, tenant_user_id: UUID) -> list[Role]:
        roles = await self._repository.get_roles_for_members(
            tenant_id=tenant_id,
            tenant_user_ids=[tenant_user_id],
        )
        return roles.get(tenant_user_id, [])

    async def _member_details(
        self,
        member: TenantMember,
        roles: list[Role],
    ) -> TenantMemberDetails:
        try:
            email = await self._email_protector.reveal(
                member.user.id,
                member.user.email_ciphertext,
            )
        except (OpenBaoError, UnicodeDecodeError) as error:
            raise ApplicationError(
                code="identity_service_unavailable",
                message="The identity service is temporarily unavailable.",
                status_code=503,
            ) from error
        return TenantMemberDetails(
            id=member.tenant_user.id,
            user_id=member.user.id,
            email=email,
            joined_at=member.tenant_user.joined_at,
            deactivated_at=member.tenant_user.deactivated_at,
            roles=tuple(
                AssignedRoleDetails(
                    id=role.id,
                    key=role.key,
                    name=role.name,
                    is_system=role.is_system,
                )
                for role in roles
            ),
        )


def _tenant_user_not_found() -> ApplicationError:
    return ApplicationError(
        code="tenant_user_not_found",
        message="The tenant user was not found.",
        status_code=404,
    )
