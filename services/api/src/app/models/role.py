from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_roles_id_tenant_id"),
        UniqueConstraint("tenant_id", "key", name="uq_roles_tenant_id_key"),
        CheckConstraint("char_length(btrim(name)) > 0", name="ck_roles_name_not_blank"),
        CheckConstraint("char_length(key) BETWEEN 1 AND 63", name="ck_roles_key_length"),
        CheckConstraint("key = lower(key)", name="ck_roles_key_lowercase"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", name="fk_roles_tenant_id_tenants", ondelete="RESTRICT"),
    )
    key: Mapped[str] = mapped_column(String(63))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(500))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
