from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LegalDocument(Base):
    __tablename__ = "legal_documents"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_legal_documents_id_tenant_id"),
        UniqueConstraint("tenant_id", "key", name="uq_legal_documents_tenant_id_key"),
        ForeignKeyConstraint(
            ["current_version_id", "id", "tenant_id"],
            [
                "legal_document_versions.id",
                "legal_document_versions.legal_document_id",
                "legal_document_versions.tenant_id",
            ],
            name="fk_legal_documents_current_version",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "char_length(key) BETWEEN 1 AND 63",
            name="ck_legal_documents_key_length",
        ),
        CheckConstraint("key = lower(key)", name="ck_legal_documents_key_lowercase"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_legal_documents_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
    )
    key: Mapped[str] = mapped_column(String(63))
    current_version_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
