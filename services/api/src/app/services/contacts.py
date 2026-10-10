import asyncio
import base64
import binascii
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.errors import ApplicationError
from app.core.tenant_context import TenantContext
from app.integrations.openbao import OpenBaoError
from app.models import Contact, ContactPii
from app.repositories.contacts import ContactRepository
from app.services.contact_data_protection import (
    ContactDataProtector,
    ProtectedValue,
    RevealedContactData,
    normalize_contact_name,
)

logger = logging.getLogger(__name__)
_IDENTIFIER_CONSTRAINTS = {
    "uq_contact_pii_tenant_email_blind_index",
    "uq_contact_pii_tenant_phone_blind_index",
}
_SENSITIVE_READ_CONCURRENCY = 10


@dataclass(frozen=True, slots=True)
class ContactPersonalDataDetails:
    name: str
    email: str | None
    phone: str | None


@dataclass(frozen=True, slots=True)
class ContactDetails:
    id: UUID
    status: str
    created_at: datetime
    updated_at: datetime
    deactivated_at: datetime | None
    personal_data: ContactPersonalDataDetails | None


@dataclass(frozen=True, slots=True)
class ContactPage:
    items: tuple[ContactDetails, ...]
    next_cursor: str | None


class ContactService:
    def __init__(
        self,
        repository: ContactRepository,
        protector: ContactDataProtector,
    ) -> None:
        self._repository = repository
        self._protector = protector

    async def create_contact(
        self,
        *,
        context: TenantContext,
        name: str,
        email: str | None,
        phone: str | None,
    ) -> ContactDetails:
        contact_id = uuid4()
        protected_name = await self._protect_name(context, contact_id, name)
        protected_email = (
            await self._protect_email(context, contact_id, email) if email is not None else None
        )
        protected_phone = (
            await self._protect_phone(context, contact_id, phone) if phone is not None else None
        )
        contact = Contact(
            id=contact_id,
            tenant_id=context.tenant_id,
            created_by_tenant_user_id=context.tenant_user_id,
            updated_by_tenant_user_id=context.tenant_user_id,
        )
        personal_data = ContactPii(
            contact_id=contact_id,
            tenant_id=context.tenant_id,
            name_ciphertext=protected_name.ciphertext,
            email_ciphertext=protected_email.ciphertext if protected_email else None,
            email_blind_index=protected_email.blind_index if protected_email else None,
            phone_ciphertext=protected_phone.ciphertext if protected_phone else None,
            phone_blind_index=protected_phone.blind_index if protected_phone else None,
        )
        try:
            async with self._repository.transaction():
                self._repository.add_contact(contact)
                self._repository.add_personal_data(personal_data)
                await self._repository.flush()
        except IntegrityError as error:
            self._raise_integrity_error(error)
        except DBAPIError as error:
            raise _persistence_unavailable() from error
        return _details(
            contact,
            ContactPersonalDataDetails(
                name=protected_name.plaintext,
                email=protected_email.plaintext if protected_email else None,
                phone=protected_phone.plaintext if protected_phone else None,
            ),
        )

    async def list_contacts(
        self,
        *,
        context: TenantContext,
        status: str,
        limit: int,
        cursor: str | None,
        include_sensitive: bool,
    ) -> ContactPage:
        cursor_created_at, cursor_id = _decode_cursor(cursor, status)
        try:
            contacts = await self._repository.list_contacts(
                tenant_id=context.tenant_id,
                status=status,
                limit=limit + 1,
                cursor_created_at=cursor_created_at,
                cursor_id=cursor_id,
            )
            has_next = len(contacts) > limit
            visible_contacts = contacts[:limit]
            personal_data = (
                await self._reveal_for_contacts(context, visible_contacts)
                if include_sensitive
                else {}
            )
        except DBAPIError as error:
            raise _persistence_unavailable() from error
        if include_sensitive:
            logger.info(
                "contact_sensitive_data_listed",
                extra={
                    "event": "contact_sensitive_data_listed",
                    "tenant_id": str(context.tenant_id),
                    "actor_user_id": str(context.user_id),
                    "contact_count": len(visible_contacts),
                },
            )
        next_cursor = (
            _encode_cursor(visible_contacts[-1], status) if has_next and visible_contacts else None
        )
        return ContactPage(
            items=tuple(
                _details(contact, personal_data.get(contact.id)) for contact in visible_contacts
            ),
            next_cursor=next_cursor,
        )

    async def get_contact(
        self,
        *,
        context: TenantContext,
        contact_id: UUID,
        include_sensitive: bool,
    ) -> ContactDetails:
        try:
            contact = await self._repository.get_contact(
                tenant_id=context.tenant_id,
                contact_id=contact_id,
            )
            if contact is None:
                raise _contact_not_found()
            personal_data = (
                await self._reveal_one(context, contact.id) if include_sensitive else None
            )
        except DBAPIError as error:
            raise _persistence_unavailable() from error
        if include_sensitive:
            _log_sensitive_read(context, contact.id, "contact_sensitive_data_viewed")
        return _details(contact, personal_data)

    async def update_contact(
        self,
        *,
        context: TenantContext,
        contact_id: UUID,
        fields: frozenset[str],
        name: str | None,
        email: str | None,
        phone: str | None,
    ) -> ContactDetails:
        protected_name = (
            await self._protect_name(context, contact_id, name)
            if "name" in fields and name is not None
            else None
        )
        protected_email = (
            await self._protect_email(context, contact_id, email)
            if "email" in fields and email is not None
            else None
        )
        protected_phone = (
            await self._protect_phone(context, contact_id, phone)
            if "phone" in fields and phone is not None
            else None
        )
        try:
            async with self._repository.transaction():
                contact = await self._repository.get_contact_for_update(
                    tenant_id=context.tenant_id,
                    contact_id=contact_id,
                )
                if contact is None:
                    raise _contact_not_found()
                if contact.deactivated_at is not None:
                    raise ApplicationError(
                        code="contact_deactivated",
                        message="A deactivated contact cannot be updated.",
                        status_code=409,
                    )
                row = await self._repository.get_personal_data_for_update(
                    tenant_id=context.tenant_id,
                    contact_id=contact_id,
                )
                if row is None:
                    raise _personal_data_unavailable()
                current = await self._reveal_row(context, row)
                result_name = current.name
                result_email = current.email
                result_phone = current.phone
                if protected_name is not None:
                    row.name_ciphertext = protected_name.ciphertext
                    result_name = protected_name.plaintext
                if "email" in fields:
                    row.email_ciphertext = protected_email.ciphertext if protected_email else None
                    row.email_blind_index = protected_email.blind_index if protected_email else None
                    result_email = protected_email.plaintext if protected_email else None
                if "phone" in fields:
                    row.phone_ciphertext = protected_phone.ciphertext if protected_phone else None
                    row.phone_blind_index = protected_phone.blind_index if protected_phone else None
                    result_phone = protected_phone.plaintext if protected_phone else None
                contact.updated_at = datetime.now(UTC)
                contact.updated_by_tenant_user_id = context.tenant_user_id
                await self._repository.flush()
        except IntegrityError as error:
            self._raise_integrity_error(error)
        except DBAPIError as error:
            raise _persistence_unavailable() from error
        _log_sensitive_read(context, contact.id, "contact_sensitive_data_updated")
        return _details(
            contact,
            ContactPersonalDataDetails(
                name=result_name,
                email=result_email,
                phone=result_phone,
            ),
        )

    async def deactivate_contact(
        self,
        *,
        context: TenantContext,
        contact_id: UUID,
    ) -> ContactDetails:
        try:
            async with self._repository.transaction():
                contact = await self._repository.get_contact_for_update(
                    tenant_id=context.tenant_id,
                    contact_id=contact_id,
                )
                if contact is None:
                    raise _contact_not_found()
                if contact.deactivated_at is None:
                    now = datetime.now(UTC)
                    contact.deactivated_at = now
                    contact.deactivated_by_tenant_user_id = context.tenant_user_id
                    contact.updated_at = now
                    contact.updated_by_tenant_user_id = context.tenant_user_id
                    await self._repository.flush()
        except DBAPIError as error:
            raise _persistence_unavailable() from error
        return _details(contact, None)

    async def search_contacts(
        self,
        *,
        context: TenantContext,
        email: str | None,
        phone: str | None,
        include_deactivated: bool,
    ) -> tuple[ContactDetails, ...]:
        try:
            email_index = (
                await self._protector.email_blind_index(
                    tenant_id=context.tenant_id,
                    email=email,
                )
                if email is not None
                else None
            )
            phone_index = (
                await self._protector.phone_blind_index(
                    tenant_id=context.tenant_id,
                    phone=phone,
                )
                if phone is not None
                else None
            )
        except ValueError as error:
            raise _phone_error(error) from error
        except OpenBaoError as error:
            raise _personal_data_unavailable() from error
        try:
            contacts = await self._repository.search_contacts(
                tenant_id=context.tenant_id,
                email_blind_index=email_index,
                phone_blind_index=phone_index,
                include_deactivated=include_deactivated,
            )
            personal_data = await self._reveal_for_contacts(context, contacts)
        except DBAPIError as error:
            raise _persistence_unavailable() from error
        logger.info(
            "contact_sensitive_data_searched",
            extra={
                "event": "contact_sensitive_data_searched",
                "tenant_id": str(context.tenant_id),
                "actor_user_id": str(context.user_id),
                "result_count": len(contacts),
            },
        )
        return tuple(_details(contact, personal_data[contact.id]) for contact in contacts)

    async def _protect_name(
        self,
        context: TenantContext,
        contact_id: UUID,
        name: str,
    ) -> ProtectedValue:
        normalized = normalize_contact_name(name)
        if not normalized or len(normalized) > 200:
            raise ApplicationError(
                code="invalid_contact_name",
                message="The contact name is invalid.",
                status_code=422,
            )
        try:
            return await self._protector.protect_name(
                tenant_id=context.tenant_id,
                contact_id=contact_id,
                name=name,
            )
        except OpenBaoError as error:
            raise _personal_data_unavailable() from error

    async def _protect_email(
        self,
        context: TenantContext,
        contact_id: UUID,
        email: str,
    ) -> ProtectedValue:
        try:
            return await self._protector.protect_email(
                tenant_id=context.tenant_id,
                contact_id=contact_id,
                email=email,
            )
        except OpenBaoError as error:
            raise _personal_data_unavailable() from error

    async def _protect_phone(
        self,
        context: TenantContext,
        contact_id: UUID,
        phone: str,
    ) -> ProtectedValue:
        try:
            return await self._protector.protect_phone(
                tenant_id=context.tenant_id,
                contact_id=contact_id,
                phone=phone,
            )
        except ValueError as error:
            raise _phone_error(error) from error
        except OpenBaoError as error:
            raise _personal_data_unavailable() from error

    async def _reveal_one(
        self,
        context: TenantContext,
        contact_id: UUID,
    ) -> ContactPersonalDataDetails:
        row = await self._repository.get_personal_data(
            tenant_id=context.tenant_id,
            contact_id=contact_id,
        )
        if row is None:
            raise _personal_data_unavailable()
        return await self._reveal_row(context, row)

    async def _reveal_for_contacts(
        self,
        context: TenantContext,
        contacts: list[Contact],
    ) -> dict[UUID, ContactPersonalDataDetails]:
        rows = await self._repository.get_personal_data_for_contacts(
            tenant_id=context.tenant_id,
            contact_ids=[contact.id for contact in contacts],
        )
        if len(rows) != len(contacts):
            raise _personal_data_unavailable()
        semaphore = asyncio.Semaphore(_SENSITIVE_READ_CONCURRENCY)

        async def reveal(row: ContactPii) -> ContactPersonalDataDetails:
            async with semaphore:
                return await self._reveal_row(context, row)

        revealed = await asyncio.gather(*(reveal(rows[contact.id]) for contact in contacts))
        return {
            contact.id: personal_data
            for contact, personal_data in zip(contacts, revealed, strict=True)
        }

    async def _reveal_row(
        self,
        context: TenantContext,
        row: ContactPii,
    ) -> ContactPersonalDataDetails:
        try:
            revealed: RevealedContactData = await self._protector.reveal(
                tenant_id=context.tenant_id,
                contact_id=row.contact_id,
                name_ciphertext=row.name_ciphertext,
                email_ciphertext=row.email_ciphertext,
                phone_ciphertext=row.phone_ciphertext,
            )
        except (OpenBaoError, UnicodeDecodeError) as error:
            raise _personal_data_unavailable() from error
        return ContactPersonalDataDetails(
            name=revealed.name,
            email=revealed.email,
            phone=revealed.phone,
        )

    @staticmethod
    def _raise_integrity_error(error: IntegrityError) -> None:
        constraint_name = getattr(error.orig, "constraint_name", None)
        if constraint_name is None and error.orig.__cause__ is not None:
            constraint_name = getattr(error.orig.__cause__, "constraint_name", None)
        if constraint_name in _IDENTIFIER_CONSTRAINTS:
            raise ApplicationError(
                code="contact_identifier_conflict",
                message="A contact with one of these identifiers already exists.",
                status_code=409,
            ) from error
        raise _persistence_unavailable() from error


def _details(
    contact: Contact,
    personal_data: ContactPersonalDataDetails | None,
) -> ContactDetails:
    return ContactDetails(
        id=contact.id,
        status="ACTIVE" if contact.deactivated_at is None else "DEACTIVATED",
        created_at=contact.created_at,
        updated_at=contact.updated_at,
        deactivated_at=contact.deactivated_at,
        personal_data=personal_data,
    )


def _encode_cursor(contact: Contact, status: str) -> str:
    payload = json.dumps(
        {
            "created_at": contact.created_at.astimezone(UTC).isoformat(),
            "id": str(contact.id),
            "status": status,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None, status: str) -> tuple[datetime | None, UUID | None]:
    if cursor is None:
        return None, None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.b64decode(padded, altchars=b"-_", validate=True))
        created_at = datetime.fromisoformat(payload["created_at"])
        contact_id = UUID(payload["id"])
        if created_at.tzinfo is None or payload["status"] != status:
            raise ValueError
    except (binascii.Error, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise ApplicationError(
            code="invalid_pagination_cursor",
            message="The pagination cursor is invalid.",
            status_code=422,
        ) from error
    return created_at, contact_id


def _log_sensitive_read(context: TenantContext, contact_id: UUID, event: str) -> None:
    logger.info(
        event,
        extra={
            "event": event,
            "tenant_id": str(context.tenant_id),
            "actor_user_id": str(context.user_id),
            "contact_id": str(contact_id),
        },
    )


def _phone_error(error: ValueError) -> ApplicationError:
    code = str(error)
    if code == "phone_country_code_required":
        return ApplicationError(
            code=code,
            message="The phone number must include an explicit international country code.",
            status_code=422,
        )
    return ApplicationError(
        code="invalid_phone_number",
        message="The phone number is invalid.",
        status_code=422,
    )


def _contact_not_found() -> ApplicationError:
    return ApplicationError(
        code="contact_not_found",
        message="The contact was not found.",
        status_code=404,
    )


def _personal_data_unavailable() -> ApplicationError:
    return ApplicationError(
        code="personal_data_service_unavailable",
        message="The personal data service is temporarily unavailable.",
        status_code=503,
    )


def _persistence_unavailable() -> ApplicationError:
    return ApplicationError(
        code="contact_persistence_unavailable",
        message="The contact service is temporarily unavailable.",
        status_code=503,
    )
