from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ContactPii(Base):
    __tablename__ = "contact_pii"
    __table_args__ = (
        ForeignKeyConstraint(
            ["contact_id", "tenant_id"],
            ["contacts.id", "contacts.tenant_id"],
            name="fk_contact_pii_contact_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "char_length(name_ciphertext) > 0",
            name="ck_contact_pii_name_ciphertext_not_empty",
        ),
        CheckConstraint(
            "(email_ciphertext IS NULL) = (email_blind_index IS NULL)",
            name="ck_contact_pii_email_pair",
        ),
        CheckConstraint(
            "email_ciphertext IS NULL OR char_length(email_ciphertext) > 0",
            name="ck_contact_pii_email_ciphertext_not_empty",
        ),
        CheckConstraint(
            "email_blind_index IS NULL OR char_length(email_blind_index) > 0",
            name="ck_contact_pii_email_blind_index_not_empty",
        ),
        CheckConstraint(
            "(phone_ciphertext IS NULL) = (phone_blind_index IS NULL)",
            name="ck_contact_pii_phone_pair",
        ),
        CheckConstraint(
            "phone_ciphertext IS NULL OR char_length(phone_ciphertext) > 0",
            name="ck_contact_pii_phone_ciphertext_not_empty",
        ),
        CheckConstraint(
            "phone_blind_index IS NULL OR char_length(phone_blind_index) > 0",
            name="ck_contact_pii_phone_blind_index_not_empty",
        ),
        Index(
            "uq_contact_pii_tenant_email_blind_index",
            "tenant_id",
            "email_blind_index",
            unique=True,
            postgresql_where=text("email_blind_index IS NOT NULL"),
        ),
        Index(
            "uq_contact_pii_tenant_phone_blind_index",
            "tenant_id",
            "phone_blind_index",
            unique=True,
            postgresql_where=text("phone_blind_index IS NOT NULL"),
        ),
    )

    contact_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    name_ciphertext: Mapped[str] = mapped_column(Text)
    email_ciphertext: Mapped[str | None] = mapped_column(Text)
    email_blind_index: Mapped[str | None] = mapped_column(String(128))
    phone_ciphertext: Mapped[str | None] = mapped_column(Text)
    phone_blind_index: Mapped[str | None] = mapped_column(String(128))
