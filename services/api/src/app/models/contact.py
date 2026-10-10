from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_contacts_id_tenant_id"),
        ForeignKeyConstraint(
            ["created_by_tenant_user_id", "tenant_id"],
            ["tenant_users.id", "tenant_users.tenant_id"],
            name="fk_contacts_creator_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["updated_by_tenant_user_id", "tenant_id"],
            ["tenant_users.id", "tenant_users.tenant_id"],
            name="fk_contacts_updater_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["deactivated_by_tenant_user_id", "tenant_id"],
            ["tenant_users.id", "tenant_users.tenant_id"],
            name="fk_contacts_deactivator_membership",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(deactivated_at IS NULL) = (deactivated_by_tenant_user_id IS NULL)",
            name="ck_contacts_deactivation_actor",
        ),
        Index(
            "ix_contacts_tenant_listing",
            "tenant_id",
            "deactivated_at",
            "created_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_contacts_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
    )
    created_by_tenant_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    updated_by_tenant_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    deactivated_by_tenant_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
