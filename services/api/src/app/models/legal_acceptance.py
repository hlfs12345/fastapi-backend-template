from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LegalAcceptance(Base):
    __tablename__ = "legal_acceptances"
    __table_args__ = (
        ForeignKeyConstraint(
            ["legal_document_version_id", "tenant_id", "acceptance_scope"],
            [
                "legal_document_versions.id",
                "legal_document_versions.tenant_id",
                "legal_document_versions.acceptance_scope",
            ],
            name="fk_legal_acceptances_version_tenant_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["actor_tenant_user_id", "tenant_id", "actor_user_id"],
            ["tenant_users.id", "tenant_users.tenant_id", "tenant_users.user_id"],
            name="fk_legal_acceptances_actor_membership",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "acceptance_scope IN ('USER', 'TENANT')",
            name="ck_legal_acceptances_acceptance_scope",
        ),
        CheckConstraint(
            "application_platform IN ('WEB', 'ANDROID', 'IOS')",
            name="ck_legal_acceptances_application_platform",
        ),
        CheckConstraint(
            "char_length(btrim(application_version)) > 0",
            name="ck_legal_acceptances_application_version_not_blank",
        ),
        CheckConstraint(
            "jsonb_typeof(actor_roles) = 'array'",
            name="ck_legal_acceptances_actor_roles_array",
        ),
        CheckConstraint(
            "jsonb_typeof(metadata) = 'object'",
            name="ck_legal_acceptances_metadata_object",
        ),
        Index(
            "uq_legal_acceptances_user_scope",
            "legal_document_version_id",
            "tenant_id",
            "actor_user_id",
            unique=True,
            postgresql_where=text("acceptance_scope = 'USER'"),
        ),
        Index(
            "uq_legal_acceptances_tenant_scope",
            "legal_document_version_id",
            "tenant_id",
            unique=True,
            postgresql_where=text("acceptance_scope = 'TENANT'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    legal_document_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    actor_tenant_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    acceptance_scope: Mapped[str] = mapped_column(String(10))
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str] = mapped_column(Text)
    application_platform: Mapped[str] = mapped_column(String(10))
    application_version: Mapped[str] = mapped_column(String(100))
    actor_roles: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB)
