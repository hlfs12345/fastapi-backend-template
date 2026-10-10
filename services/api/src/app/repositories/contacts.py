from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from app.models import Contact, ContactPii


class ContactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def transaction(self) -> AsyncSessionTransaction:
        return self._session.begin()

    def add_contact(self, contact: Contact) -> None:
        self._session.add(contact)

    def add_personal_data(self, personal_data: ContactPii) -> None:
        self._session.add(personal_data)

    async def flush(self) -> None:
        await self._session.flush()

    async def get_contact(self, *, tenant_id: UUID, contact_id: UUID) -> Contact | None:
        statement = select(Contact).where(
            Contact.tenant_id == tenant_id,
            Contact.id == contact_id,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_contact_for_update(
        self,
        *,
        tenant_id: UUID,
        contact_id: UUID,
    ) -> Contact | None:
        statement = (
            select(Contact)
            .where(
                Contact.tenant_id == tenant_id,
                Contact.id == contact_id,
            )
            .with_for_update(of=Contact)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_personal_data(
        self,
        *,
        tenant_id: UUID,
        contact_id: UUID,
    ) -> ContactPii | None:
        statement = select(ContactPii).where(
            ContactPii.tenant_id == tenant_id,
            ContactPii.contact_id == contact_id,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_personal_data_for_update(
        self,
        *,
        tenant_id: UUID,
        contact_id: UUID,
    ) -> ContactPii | None:
        statement = (
            select(ContactPii)
            .where(
                ContactPii.tenant_id == tenant_id,
                ContactPii.contact_id == contact_id,
            )
            .with_for_update(of=ContactPii)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_personal_data_for_contacts(
        self,
        *,
        tenant_id: UUID,
        contact_ids: list[UUID],
    ) -> dict[UUID, ContactPii]:
        if not contact_ids:
            return {}
        statement = select(ContactPii).where(
            ContactPii.tenant_id == tenant_id,
            ContactPii.contact_id.in_(contact_ids),
        )
        rows = (await self._session.execute(statement)).scalars()
        return {row.contact_id: row for row in rows}

    async def list_contacts(
        self,
        *,
        tenant_id: UUID,
        status: str,
        limit: int,
        cursor_created_at: datetime | None,
        cursor_id: UUID | None,
    ) -> list[Contact]:
        statement = select(Contact).where(Contact.tenant_id == tenant_id)
        if status == "ACTIVE":
            statement = statement.where(Contact.deactivated_at.is_(None))
        elif status == "DEACTIVATED":
            statement = statement.where(Contact.deactivated_at.is_not(None))
        if cursor_created_at is not None and cursor_id is not None:
            statement = statement.where(
                or_(
                    Contact.created_at < cursor_created_at,
                    and_(
                        Contact.created_at == cursor_created_at,
                        Contact.id < cursor_id,
                    ),
                )
            )
        statement = statement.order_by(Contact.created_at.desc(), Contact.id.desc()).limit(limit)
        return list((await self._session.execute(statement)).scalars())

    async def search_contacts(
        self,
        *,
        tenant_id: UUID,
        email_blind_index: str | None,
        phone_blind_index: str | None,
        include_deactivated: bool,
    ) -> list[Contact]:
        statement = (
            select(Contact)
            .join(
                ContactPii,
                and_(
                    ContactPii.contact_id == Contact.id,
                    ContactPii.tenant_id == Contact.tenant_id,
                ),
            )
            .where(Contact.tenant_id == tenant_id)
        )
        if email_blind_index is not None:
            statement = statement.where(ContactPii.email_blind_index == email_blind_index)
        if phone_blind_index is not None:
            statement = statement.where(ContactPii.phone_blind_index == phone_blind_index)
        if not include_deactivated:
            statement = statement.where(Contact.deactivated_at.is_(None))
        statement = statement.order_by(Contact.created_at.desc(), Contact.id.desc()).limit(1)
        return list((await self._session.execute(statement)).scalars())
