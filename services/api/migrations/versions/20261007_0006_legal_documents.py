"""Add tenant legal documents and immutable versions.

Revision ID: 20261007_0006
Revises: 20261007_0005
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261007_0006"
down_revision: str | None = "20261007_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_tenant_users_id_tenant_id_user_id",
        "tenant_users",
        ["id", "tenant_id", "user_id"],
    )
    op.create_table(
        "legal_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=63), nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(key) BETWEEN 1 AND 63",
            name="ck_legal_documents_key_length",
        ),
        sa.CheckConstraint(
            "key = lower(key)",
            name="ck_legal_documents_key_lowercase",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_legal_documents_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_legal_documents"),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            name="uq_legal_documents_id_tenant_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "key",
            name="uq_legal_documents_tenant_id_key",
        ),
    )
    op.create_table(
        "legal_document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("legal_document_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("acceptance_scope", sa.String(length=10), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("published_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("published_by_tenant_user_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "version > 0",
            name="ck_legal_document_versions_version_positive",
        ),
        sa.CheckConstraint(
            "char_length(btrim(title)) > 0",
            name="ck_legal_document_versions_title_not_blank",
        ),
        sa.CheckConstraint(
            "char_length(content) > 0",
            name="ck_legal_document_versions_content_not_empty",
        ),
        sa.CheckConstraint(
            "acceptance_scope IN ('USER', 'TENANT')",
            name="ck_legal_document_versions_acceptance_scope",
        ),
        sa.ForeignKeyConstraint(
            ["legal_document_id", "tenant_id"],
            ["legal_documents.id", "legal_documents.tenant_id"],
            name="fk_legal_document_versions_document_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["published_by_tenant_user_id", "tenant_id", "published_by_user_id"],
            ["tenant_users.id", "tenant_users.tenant_id", "tenant_users.user_id"],
            name="fk_legal_document_versions_publisher_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_legal_document_versions"),
        sa.UniqueConstraint(
            "legal_document_id",
            "version",
            name="uq_legal_document_versions_document_version",
        ),
        sa.UniqueConstraint(
            "id",
            "legal_document_id",
            "tenant_id",
            name="uq_legal_document_versions_id_document_tenant",
        ),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            "acceptance_scope",
            name="uq_legal_document_versions_id_tenant_scope",
        ),
    )
    op.create_foreign_key(
        "fk_legal_documents_current_version",
        "legal_documents",
        "legal_document_versions",
        ["current_version_id", "id", "tenant_id"],
        ["id", "legal_document_id", "tenant_id"],
        ondelete="RESTRICT",
    )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION prevent_legal_history_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION '% records are immutable', TG_TABLE_NAME;
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_legal_document_versions_immutable
            BEFORE UPDATE OR DELETE ON legal_document_versions
            FOR EACH ROW EXECUTE FUNCTION prevent_legal_history_mutation()
            """
        )
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_legal_document_versions_immutable ON legal_document_versions")
    op.execute("DROP FUNCTION prevent_legal_history_mutation()")
    op.drop_constraint(
        "fk_legal_documents_current_version",
        "legal_documents",
        type_="foreignkey",
    )
    op.drop_table("legal_document_versions")
    op.drop_table("legal_documents")
    op.drop_constraint(
        "uq_tenant_users_id_tenant_id_user_id",
        "tenant_users",
        type_="unique",
    )
