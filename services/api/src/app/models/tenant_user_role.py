from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKeyConstraint, Index, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TenantUserRole(Base):
    __tablename__ = "tenant_user_roles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_user_id", "tenant_id"],
            ["tenant_users.id", "tenant_users.tenant_id"],
            name="fk_tenant_user_roles_member_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["role_id", "tenant_id"],
            ["roles.id", "roles.tenant_id"],
            name="fk_tenant_user_roles_role_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["assigned_by_tenant_user_id", "tenant_id"],
            ["tenant_users.id", "tenant_users.tenant_id"],
            name="fk_tenant_user_roles_assigner_tenant",
            ondelete="RESTRICT",
        ),
        Index("ix_tenant_user_roles_role", "tenant_id", "role_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    role_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    assigned_by_tenant_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
