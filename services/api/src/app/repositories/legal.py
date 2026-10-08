from uuid import UUID

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from app.core.legal import LegalAcceptanceScope
from app.models import (
    LegalAcceptance,
    LegalDocument,
    LegalDocumentVersion,
    Role,
    TenantUserRole,
)


class LegalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def transaction(self) -> AsyncSessionTransaction:
        return self._session.begin()

    async def get_document_by_key(
        self,
        *,
        tenant_id: UUID,
        key: str,
    ) -> LegalDocument | None:
        statement = select(LegalDocument).where(
            LegalDocument.tenant_id == tenant_id,
            LegalDocument.key == key,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_document_for_update(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> LegalDocument | None:
        statement = (
            select(LegalDocument)
            .where(
                LegalDocument.tenant_id == tenant_id,
                LegalDocument.id == document_id,
            )
            .with_for_update(of=LegalDocument)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_current_version(
        self,
        document: LegalDocument,
    ) -> LegalDocumentVersion | None:
        if document.current_version_id is None:
            return None
        statement = select(LegalDocumentVersion).where(
            LegalDocumentVersion.tenant_id == document.tenant_id,
            LegalDocumentVersion.legal_document_id == document.id,
            LegalDocumentVersion.id == document.current_version_id,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_current_versions(
        self,
        tenant_id: UUID,
    ) -> list[tuple[LegalDocument, LegalDocumentVersion]]:
        statement = (
            select(LegalDocument, LegalDocumentVersion)
            .join(
                LegalDocument,
                and_(
                    LegalDocument.current_version_id == LegalDocumentVersion.id,
                    LegalDocument.id == LegalDocumentVersion.legal_document_id,
                    LegalDocument.tenant_id == LegalDocumentVersion.tenant_id,
                ),
            )
            .where(LegalDocument.tenant_id == tenant_id)
            .order_by(LegalDocument.key, LegalDocumentVersion.version)
        )
        return [(row[0], row[1]) for row in (await self._session.execute(statement)).all()]

    async def list_pending_versions(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
    ) -> list[tuple[LegalDocument, LegalDocumentVersion]]:
        accepted = exists(
            select(LegalAcceptance.id).where(
                LegalAcceptance.tenant_id == tenant_id,
                LegalAcceptance.legal_document_version_id == LegalDocumentVersion.id,
                or_(
                    LegalAcceptance.acceptance_scope == LegalAcceptanceScope.TENANT.value,
                    and_(
                        LegalAcceptance.acceptance_scope == LegalAcceptanceScope.USER.value,
                        LegalAcceptance.actor_user_id == user_id,
                    ),
                ),
            )
        )
        statement = (
            select(LegalDocument, LegalDocumentVersion)
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
        return [(row[0], row[1]) for row in (await self._session.execute(statement)).all()]

    async def get_version(
        self,
        *,
        tenant_id: UUID,
        version_id: UUID,
    ) -> tuple[LegalDocument, LegalDocumentVersion] | None:
        statement = (
            select(LegalDocument, LegalDocumentVersion)
            .join(
                LegalDocumentVersion,
                and_(
                    LegalDocumentVersion.legal_document_id == LegalDocument.id,
                    LegalDocumentVersion.tenant_id == LegalDocument.tenant_id,
                ),
            )
            .where(
                LegalDocument.tenant_id == tenant_id,
                LegalDocumentVersion.id == version_id,
            )
        )
        row = (await self._session.execute(statement)).one_or_none()
        return (row[0], row[1]) if row else None

    async def get_acceptance(
        self,
        *,
        tenant_id: UUID,
        version_id: UUID,
        user_id: UUID,
        acceptance_scope: str,
    ) -> LegalAcceptance | None:
        statement = select(LegalAcceptance).where(
            LegalAcceptance.tenant_id == tenant_id,
            LegalAcceptance.legal_document_version_id == version_id,
            LegalAcceptance.acceptance_scope == acceptance_scope,
        )
        if acceptance_scope == LegalAcceptanceScope.USER.value:
            statement = statement.where(LegalAcceptance.actor_user_id == user_id)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def create_acceptance_if_absent(self, acceptance: LegalAcceptance) -> None:
        statement = (
            insert(LegalAcceptance)
            .values(
                id=acceptance.id,
                tenant_id=acceptance.tenant_id,
                legal_document_version_id=acceptance.legal_document_version_id,
                actor_user_id=acceptance.actor_user_id,
                actor_tenant_user_id=acceptance.actor_tenant_user_id,
                acceptance_scope=acceptance.acceptance_scope,
                ip_address=acceptance.ip_address,
                user_agent=acceptance.user_agent,
                application_platform=acceptance.application_platform,
                application_version=acceptance.application_version,
                actor_roles=acceptance.actor_roles,
                metadata=acceptance.metadata_,
            )
            .on_conflict_do_nothing()
        )
        await self._session.execute(statement)

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
            .order_by(Role.key, Role.id)
        )
        return list((await self._session.execute(statement)).scalars())

    def add_document(self, document: LegalDocument) -> None:
        self._session.add(document)

    def add_version(self, version: LegalDocumentVersion) -> None:
        self._session.add(version)

    async def flush(self) -> None:
        await self._session.flush()
