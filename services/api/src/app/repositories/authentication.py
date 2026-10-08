from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, and_, exists, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from app.core.security import AccessTokenClaims
from app.core.tenant_context import TenantContext
from app.models import (
    LegalAcceptance,
    LegalDocument,
    LegalDocumentVersion,
    RefreshSession,
    Role,
    RolePermission,
    Tenant,
    TenantUser,
    TenantUserRole,
    User,
)


@dataclass(frozen=True, slots=True)
class AuthenticationIdentity:
    user: User
    tenant: Tenant
    tenant_user: TenantUser


@dataclass(frozen=True, slots=True)
class RefreshIdentity:
    refresh_session: RefreshSession
    user: User
    tenant: Tenant
    tenant_user: TenantUser

    def is_active(self) -> bool:
        return (
            self.user.disabled_at is None
            and self.tenant.deactivated_at is None
            and self.tenant_user.deactivated_at is None
            and self.tenant_user.user_id == self.user.id
            and self.tenant_user.tenant_id == self.tenant.id
        )


class AuthenticationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def transaction(self) -> AsyncSessionTransaction:
        return self._session.begin()

    async def get_login_identity(
        self,
        *,
        email_blind_index: str,
        tenant_slug: str,
    ) -> AuthenticationIdentity | None:
        statement = (
            self._identity_statement()
            .where(
                User.email_blind_index == email_blind_index,
                Tenant.slug == tenant_slug,
                User.disabled_at.is_(None),
                Tenant.deactivated_at.is_(None),
                TenantUser.deactivated_at.is_(None),
            )
            .with_for_update(of=User)
        )
        row = (await self._session.execute(statement)).one_or_none()
        return AuthenticationIdentity(*row) if row else None

    async def get_authenticated_identity(
        self,
        context: TenantContext,
    ) -> AuthenticationIdentity | None:
        statement = self._active_identity_statement(context)
        row = (await self._session.execute(statement)).one_or_none()
        return AuthenticationIdentity(*row) if row else None

    async def get_authenticated_identity_for_update(
        self,
        context: TenantContext,
    ) -> AuthenticationIdentity | None:
        statement = self._active_identity_statement(context).with_for_update(of=User)
        row = (await self._session.execute(statement)).one_or_none()
        return AuthenticationIdentity(*row) if row else None

    async def get_active_roles(
        self,
        *,
        tenant_id: UUID,
        tenant_user_id: UUID,
    ) -> list[Role]:
        statement = (
            select(Role)
            .join(
                TenantUserRole,
                and_(
                    TenantUserRole.role_id == Role.id,
                    TenantUserRole.tenant_id == Role.tenant_id,
                ),
            )
            .where(
                Role.tenant_id == tenant_id,
                TenantUserRole.tenant_user_id == tenant_user_id,
                Role.deactivated_at.is_(None),
            )
            .order_by(Role.name, Role.key, Role.id)
        )
        return list((await self._session.execute(statement)).scalars())

    async def get_active_tenant_context(
        self,
        claims: AccessTokenClaims,
    ) -> TenantContext | None:
        statement = self._identity_statement().where(
            User.id == claims.user_id,
            Tenant.id == claims.tenant_id,
            TenantUser.id == claims.tenant_user_id,
            User.disabled_at.is_(None),
            Tenant.deactivated_at.is_(None),
            TenantUser.deactivated_at.is_(None),
        )
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        user, tenant, tenant_user = row
        permissions = await self._get_permissions(
            tenant_id=tenant.id,
            tenant_user_id=tenant_user.id,
        )
        pending_legal_version_ids = await self._get_pending_legal_version_ids(
            tenant_id=tenant.id,
            user_id=user.id,
        )
        return TenantContext(
            tenant_id=tenant.id,
            user_id=user.id,
            tenant_user_id=tenant_user.id,
            permissions=permissions,
            pending_legal_version_ids=pending_legal_version_ids,
        )

    async def get_refresh_identity_for_update(
        self,
        token_hash: bytes,
    ) -> RefreshIdentity | None:
        user_id = (
            await self._session.execute(
                select(RefreshSession.user_id).where(RefreshSession.token_hash == token_hash)
            )
        ).scalar_one_or_none()
        if user_id is None:
            return None

        await self._session.execute(
            select(User.id).where(User.id == user_id).with_for_update(of=User)
        )
        statement = (
            select(RefreshSession, User, Tenant, TenantUser)
            .join(User, User.id == RefreshSession.user_id)
            .join(TenantUser, TenantUser.id == RefreshSession.tenant_user_id)
            .join(Tenant, Tenant.id == TenantUser.tenant_id)
            .where(RefreshSession.token_hash == token_hash)
            .with_for_update(of=RefreshSession)
        )
        row = (await self._session.execute(statement)).one_or_none()
        return RefreshIdentity(*row) if row else None

    def add_refresh_session(self, refresh_session: RefreshSession) -> None:
        self._session.add(refresh_session)

    async def _get_permissions(
        self,
        *,
        tenant_id: UUID,
        tenant_user_id: UUID,
    ) -> frozenset[str]:
        statement = (
            select(RolePermission.permission_code)
            .select_from(TenantUserRole)
            .join(
                Role,
                and_(
                    Role.id == TenantUserRole.role_id,
                    Role.tenant_id == TenantUserRole.tenant_id,
                ),
            )
            .join(
                RolePermission,
                and_(
                    RolePermission.role_id == Role.id,
                    RolePermission.tenant_id == Role.tenant_id,
                ),
            )
            .where(
                TenantUserRole.tenant_id == tenant_id,
                TenantUserRole.tenant_user_id == tenant_user_id,
                Role.deactivated_at.is_(None),
            )
            .distinct()
        )
        return frozenset((await self._session.execute(statement)).scalars())

    async def _get_pending_legal_version_ids(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
    ) -> tuple[UUID, ...]:
        accepted = exists(
            select(LegalAcceptance.id).where(
                LegalAcceptance.tenant_id == tenant_id,
                LegalAcceptance.legal_document_version_id == LegalDocumentVersion.id,
                or_(
                    LegalAcceptance.acceptance_scope == "TENANT",
                    and_(
                        LegalAcceptance.acceptance_scope == "USER",
                        LegalAcceptance.actor_user_id == user_id,
                    ),
                ),
            )
        )
        statement = (
            select(LegalDocumentVersion.id)
            .join(
                LegalDocument,
                and_(
                    LegalDocument.current_version_id == LegalDocumentVersion.id,
                    LegalDocument.id == LegalDocumentVersion.legal_document_id,
                    LegalDocument.tenant_id == LegalDocumentVersion.tenant_id,
                ),
            )
            .where(
                LegalDocument.tenant_id == tenant_id,
                LegalDocumentVersion.is_required.is_(True),
                ~accepted,
            )
            .order_by(LegalDocument.key, LegalDocumentVersion.version)
        )
        return tuple((await self._session.execute(statement)).scalars())

    async def revoke_family(self, family_id: UUID, revoked_at: datetime) -> None:
        await self._session.execute(
            update(RefreshSession)
            .where(
                RefreshSession.family_id == family_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )

    async def revoke_user_sessions(self, user_id: UUID, revoked_at: datetime) -> None:
        await self._session.execute(
            update(RefreshSession)
            .where(
                RefreshSession.user_id == user_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )

    @staticmethod
    def _identity_statement() -> Select[tuple[User, Tenant, TenantUser]]:
        return (
            select(User, Tenant, TenantUser)
            .join(TenantUser, TenantUser.user_id == User.id)
            .join(Tenant, Tenant.id == TenantUser.tenant_id)
        )

    @classmethod
    def _active_identity_statement(
        cls,
        context: TenantContext,
    ) -> Select[tuple[User, Tenant, TenantUser]]:
        return cls._identity_statement().where(
            User.id == context.user_id,
            Tenant.id == context.tenant_id,
            TenantUser.id == context.tenant_user_id,
            User.disabled_at.is_(None),
            Tenant.deactivated_at.is_(None),
            TenantUser.deactivated_at.is_(None),
        )
