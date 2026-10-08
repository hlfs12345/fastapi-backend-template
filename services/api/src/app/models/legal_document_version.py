from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LegalDocumentVersion(Base):
    __tablename__ = "legal_document_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["legal_document_id", "tenant_id"],
            ["legal_documents.id", "legal_documents.tenant_id"],
            name="fk_legal_document_versions_document_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["published_by_tenant_user_id", "tenant_id", "published_by_user_id"],
            ["tenant_users.id", "tenant_users.tenant_id", "tenant_users.user_id"],
            name="fk_legal_document_versions_publisher_membership",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "legal_document_id",
            "version",
            name="uq_legal_document_versions_document_version",
        ),
        UniqueConstraint(
            "id",
            "legal_document_id",
            "tenant_id",
            name="uq_legal_document_versions_id_document_tenant",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            "acceptance_scope",
            name="uq_legal_document_versions_id_tenant_scope",
        ),
        CheckConstraint("version > 0", name="ck_legal_document_versions_version_positive"),
        CheckConstraint(
            "char_length(btrim(title)) > 0",
            name="ck_legal_document_versions_title_not_blank",
        ),
        CheckConstraint(
            "char_length(content) > 0",
            name="ck_legal_document_versions_content_not_empty",
        ),
        CheckConstraint(
            "acceptance_scope IN ('USER', 'TENANT')",
            name="ck_legal_document_versions_acceptance_scope",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    legal_document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    acceptance_scope: Mapped[str] = mapped_column(String(10))
    is_required: Mapped[bool] = mapped_column(Boolean)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    published_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    published_by_tenant_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
