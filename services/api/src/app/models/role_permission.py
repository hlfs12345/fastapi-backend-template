from uuid import UUID

from sqlalchemy import ForeignKey, ForeignKeyConstraint, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["role_id", "tenant_id"],
            ["roles.id", "roles.tenant_id"],
            name="fk_role_permissions_role_tenant_roles",
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    role_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    permission_code: Mapped[str] = mapped_column(
        String(100),
        ForeignKey(
            "permissions.code",
            name="fk_role_permissions_permission_code_permissions",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )
