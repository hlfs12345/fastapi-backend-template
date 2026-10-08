"""Add immutable legal acceptances.

Revision ID: 20261007_0007
Revises: 20261007_0006
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261007_0007"
down_revision: str | None = "20261007_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "legal_acceptances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("legal_document_version_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("actor_tenant_user_id", sa.Uuid(), nullable=False),
        sa.Column("acceptance_scope", sa.String(length=10), nullable=False),
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=False),
        sa.Column("application_platform", sa.String(length=10), nullable=False),
        sa.Column("application_version", sa.String(length=100), nullable=False),
        sa.Column("actor_roles", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.CheckConstraint(
            "acceptance_scope IN ('USER', 'TENANT')",
            name="ck_legal_acceptances_acceptance_scope",
        ),
        sa.CheckConstraint(
            "application_platform IN ('WEB', 'ANDROID', 'IOS')",
            name="ck_legal_acceptances_application_platform",
        ),
        sa.CheckConstraint(
            "char_length(btrim(application_version)) > 0",
            name="ck_legal_acceptances_application_version_not_blank",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(actor_roles) = 'array'",
            name="ck_legal_acceptances_actor_roles_array",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(metadata) = 'object'",
            name="ck_legal_acceptances_metadata_object",
        ),
        sa.ForeignKeyConstraint(
            ["legal_document_version_id", "tenant_id", "acceptance_scope"],
            [
                "legal_document_versions.id",
                "legal_document_versions.tenant_id",
                "legal_document_versions.acceptance_scope",
            ],
            name="fk_legal_acceptances_version_tenant_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_tenant_user_id", "tenant_id", "actor_user_id"],
            ["tenant_users.id", "tenant_users.tenant_id", "tenant_users.user_id"],
            name="fk_legal_acceptances_actor_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_legal_acceptances"),
    )
    op.create_index(
        "uq_legal_acceptances_user_scope",
        "legal_acceptances",
        ["legal_document_version_id", "tenant_id", "actor_user_id"],
        unique=True,
        postgresql_where=sa.text("acceptance_scope = 'USER'"),
    )
    op.create_index(
        "uq_legal_acceptances_tenant_scope",
        "legal_acceptances",
        ["legal_document_version_id", "tenant_id"],
        unique=True,
        postgresql_where=sa.text("acceptance_scope = 'TENANT'"),
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_legal_acceptances_immutable
            BEFORE UPDATE OR DELETE ON legal_acceptances
            FOR EACH ROW EXECUTE FUNCTION prevent_legal_history_mutation()
            """
        )
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_legal_acceptances_immutable ON legal_acceptances")
    op.drop_index(
        "uq_legal_acceptances_tenant_scope",
        table_name="legal_acceptances",
    )
    op.drop_index(
        "uq_legal_acceptances_user_scope",
        table_name="legal_acceptances",
    )
    op.drop_table("legal_acceptances")
