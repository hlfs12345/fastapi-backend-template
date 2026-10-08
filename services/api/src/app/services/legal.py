import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.core.errors import ApplicationError
from app.core.legal import ApplicationPlatform, LegalAcceptanceScope
from app.core.permissions import LEGAL_ACCEPT_FOR_TENANT
from app.core.tenant_context import TenantContext
from app.models import LegalAcceptance, LegalDocument, LegalDocumentVersion
from app.repositories.legal import LegalRepository

_DOCUMENT_KEY_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_MAX_CONTENT_LENGTH = 1_000_000
_MAX_METADATA_BYTES = 8 * 1024


@dataclass(frozen=True, slots=True)
class LegalVersionDetails:
    document_id: UUID
    document_key: str
    version_id: UUID
    version: int
    title: str
    content: str
    acceptance_scope: str
    is_required: bool
    published_at: datetime


@dataclass(frozen=True, slots=True)
class LegalAcceptanceDetails:
    id: UUID
    legal_document_version_id: UUID
    acceptance_scope: str
    accepted_at: datetime
    application_platform: str
    application_version: str
    actor_roles: tuple[dict[str, Any], ...]
    metadata: dict[str, Any]


class LegalService:
    def __init__(self, repository: LegalRepository) -> None:
        self._repository = repository

    async def create_document(
        self,
        *,
        context: TenantContext,
        key: str,
        title: str,
        content: str,
        acceptance_scope: LegalAcceptanceScope,
        is_required: bool,
    ) -> LegalVersionDetails:
        normalized_title = _validate_publication(
            key=key,
            title=title,
            content=content,
        )
        document = LegalDocument(
            id=uuid4(),
            tenant_id=context.tenant_id,
            key=key,
        )
        version = self._new_version(
            context=context,
            document_id=document.id,
            version_number=1,
            title=normalized_title,
            content=content,
            acceptance_scope=acceptance_scope,
            is_required=is_required,
        )
        try:
            async with self._repository.transaction():
                if (
                    await self._repository.get_document_by_key(
                        tenant_id=context.tenant_id,
                        key=key,
                    )
                    is not None
                ):
                    raise _document_key_conflict()
                self._repository.add_document(document)
                await self._repository.flush()
                self._repository.add_version(version)
                await self._repository.flush()
                document.current_version_id = version.id
                await self._repository.flush()
        except IntegrityError as error:
            raise _document_key_conflict() from error
        return _version_details(document, version)

    async def publish_version(
        self,
        *,
        context: TenantContext,
        document_id: UUID,
        title: str,
        content: str,
        acceptance_scope: LegalAcceptanceScope,
        is_required: bool,
    ) -> LegalVersionDetails:
        normalized_title = _validate_publication(
            key="valid",
            title=title,
            content=content,
        )
        async with self._repository.transaction():
            document = await self._repository.get_document_for_update(
                tenant_id=context.tenant_id,
                document_id=document_id,
            )
            if document is None:
                raise _document_not_found()
            current_version = await self._repository.get_current_version(document)
            if current_version is None:
                raise ApplicationError(
                    code="legal_document_invalid_state",
                    message="The legal document has no current version.",
                    status_code=409,
                )
            version = self._new_version(
                context=context,
                document_id=document.id,
                version_number=current_version.version + 1,
                title=normalized_title,
                content=content,
                acceptance_scope=acceptance_scope,
                is_required=is_required,
            )
            self._repository.add_version(version)
            await self._repository.flush()
            document.current_version_id = version.id
            await self._repository.flush()
        return _version_details(document, version)

    async def list_current_versions(
        self,
        context: TenantContext,
    ) -> list[LegalVersionDetails]:
        rows = await self._repository.list_current_versions(context.tenant_id)
        return [_version_details(document, version) for document, version in rows]

    async def list_pending_versions(
        self,
        context: TenantContext,
    ) -> list[LegalVersionDetails]:
        rows = await self._repository.list_pending_versions(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
        )
        return [_version_details(document, version) for document, version in rows]

    async def get_visible_version(
        self,
        *,
        context: TenantContext,
        version_id: UUID,
    ) -> LegalVersionDetails:
        row = await self._repository.get_version(
            tenant_id=context.tenant_id,
            version_id=version_id,
        )
        if row is None:
            raise _version_not_found()
        document, version = row
        if document.current_version_id != version.id:
            acceptance = await self._repository.get_acceptance(
                tenant_id=context.tenant_id,
                version_id=version.id,
                user_id=context.user_id,
                acceptance_scope=version.acceptance_scope,
            )
            if acceptance is None:
                raise _version_not_found()
        return _version_details(document, version)

    async def accept_version(
        self,
        *,
        context: TenantContext,
        version_id: UUID,
        application_platform: ApplicationPlatform,
        application_version: str,
        metadata: dict[str, Any],
        ip_address: str | None,
        user_agent: str,
    ) -> LegalAcceptanceDetails:
        _validate_acceptance_input(application_version, metadata)
        async with self._repository.transaction():
            row = await self._repository.get_version(
                tenant_id=context.tenant_id,
                version_id=version_id,
            )
            if row is None:
                raise _version_not_found()
            document, version = row
            if (
                version.acceptance_scope == LegalAcceptanceScope.TENANT.value
                and LEGAL_ACCEPT_FOR_TENANT not in context.permissions
            ):
                raise ApplicationError(
                    code="permission_denied",
                    message="Permission denied.",
                    status_code=403,
                )
            existing = await self._repository.get_acceptance(
                tenant_id=context.tenant_id,
                version_id=version.id,
                user_id=context.user_id,
                acceptance_scope=version.acceptance_scope,
            )
            if existing is not None:
                return _acceptance_details(existing)
            if document.current_version_id != version.id:
                raise ApplicationError(
                    code="legal_version_superseded",
                    message="The legal document version is no longer current.",
                    status_code=409,
                    details={"current_version_id": str(document.current_version_id)},
                )
            roles = await self._repository.get_active_roles(
                tenant_id=context.tenant_id,
                tenant_user_id=context.tenant_user_id,
            )
            acceptance = LegalAcceptance(
                id=uuid4(),
                tenant_id=context.tenant_id,
                legal_document_version_id=version.id,
                actor_user_id=context.user_id,
                actor_tenant_user_id=context.tenant_user_id,
                acceptance_scope=version.acceptance_scope,
                ip_address=ip_address,
                user_agent=user_agent,
                application_platform=application_platform.value,
                application_version=application_version,
                actor_roles=[
                    {"id": str(role.id), "key": role.key, "name": role.name} for role in roles
                ],
                metadata_=metadata,
            )
            await self._repository.create_acceptance_if_absent(acceptance)
            persisted = await self._repository.get_acceptance(
                tenant_id=context.tenant_id,
                version_id=version.id,
                user_id=context.user_id,
                acceptance_scope=version.acceptance_scope,
            )
            if persisted is None:
                raise RuntimeError("Legal acceptance was not persisted.")
            return _acceptance_details(persisted)

    def _new_version(
        self,
        *,
        context: TenantContext,
        document_id: UUID,
        version_number: int,
        title: str,
        content: str,
        acceptance_scope: LegalAcceptanceScope,
        is_required: bool,
    ) -> LegalDocumentVersion:
        return LegalDocumentVersion(
            id=uuid4(),
            tenant_id=context.tenant_id,
            legal_document_id=document_id,
            version=version_number,
            title=title,
            content=content,
            acceptance_scope=acceptance_scope.value,
            is_required=is_required,
            published_by_user_id=context.user_id,
            published_by_tenant_user_id=context.tenant_user_id,
        )


def _validate_publication(*, key: str, title: str, content: str) -> str:
    normalized_title = title.strip()
    if not _DOCUMENT_KEY_PATTERN.fullmatch(key) or not 1 <= len(key) <= 63:
        raise _invalid_document()
    if not normalized_title or len(normalized_title) > 200:
        raise _invalid_document()
    if not content.strip() or len(content) > _MAX_CONTENT_LENGTH:
        raise _invalid_document()
    return normalized_title


def _validate_acceptance_input(
    application_version: str,
    metadata: dict[str, Any],
) -> None:
    if not application_version.strip() or len(application_version) > 100:
        raise ApplicationError(
            code="invalid_legal_acceptance",
            message="The legal acceptance data is invalid.",
            status_code=422,
        )
    try:
        metadata_size = len(
            json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
    except (TypeError, ValueError) as error:
        raise ApplicationError(
            code="invalid_legal_acceptance",
            message="The legal acceptance data is invalid.",
            status_code=422,
        ) from error
    if metadata_size > _MAX_METADATA_BYTES:
        raise ApplicationError(
            code="legal_acceptance_metadata_too_large",
            message="The legal acceptance metadata is too large.",
            status_code=422,
        )


def _version_details(
    document: LegalDocument,
    version: LegalDocumentVersion,
) -> LegalVersionDetails:
    return LegalVersionDetails(
        document_id=document.id,
        document_key=document.key,
        version_id=version.id,
        version=version.version,
        title=version.title,
        content=version.content,
        acceptance_scope=version.acceptance_scope,
        is_required=version.is_required,
        published_at=version.published_at,
    )


def _acceptance_details(acceptance: LegalAcceptance) -> LegalAcceptanceDetails:
    return LegalAcceptanceDetails(
        id=acceptance.id,
        legal_document_version_id=acceptance.legal_document_version_id,
        acceptance_scope=acceptance.acceptance_scope,
        accepted_at=acceptance.accepted_at,
        application_platform=acceptance.application_platform,
        application_version=acceptance.application_version,
        actor_roles=tuple(acceptance.actor_roles),
        metadata=acceptance.metadata_,
    )


def _invalid_document() -> ApplicationError:
    return ApplicationError(
        code="invalid_legal_document",
        message="The legal document data is invalid.",
        status_code=422,
    )


def _document_key_conflict() -> ApplicationError:
    return ApplicationError(
        code="legal_document_key_conflict",
        message="A legal document with this key already exists in the tenant.",
        status_code=409,
    )


def _document_not_found() -> ApplicationError:
    return ApplicationError(
        code="legal_document_not_found",
        message="The legal document was not found.",
        status_code=404,
    )


def _version_not_found() -> ApplicationError:
    return ApplicationError(
        code="legal_document_version_not_found",
        message="The legal document version was not found.",
        status_code=404,
    )
