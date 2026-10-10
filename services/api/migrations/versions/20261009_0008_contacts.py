"""Add tenant-scoped contacts and protected personal data.

Revision ID: 20261009_0008
Revises: 20261007_0007
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261009_0008"
down_revision: str | None = "20261007_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_tenant_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_tenant_user_id", sa.Uuid(), nullable=False),
        sa.Column("deactivated_by_tenant_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(deactivated_at IS NULL) = (deactivated_by_tenant_user_id IS NULL)",
            name="ck_contacts_deactivation_actor",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_contacts_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_tenant_user_id", "tenant_id"],
            ["tenant_users.id", "tenant_users.tenant_id"],
            name="fk_contacts_creator_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_tenant_user_id", "tenant_id"],
            ["tenant_users.id", "tenant_users.tenant_id"],
            name="fk_contacts_updater_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["deactivated_by_tenant_user_id", "tenant_id"],
            ["tenant_users.id", "tenant_users.tenant_id"],
            name="fk_contacts_deactivator_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_contacts"),
        sa.UniqueConstraint("id", "tenant_id", name="uq_contacts_id_tenant_id"),
    )
    op.create_index(
        "ix_contacts_tenant_listing",
        "contacts",
        ["tenant_id", "deactivated_at", "created_at", "id"],
    )
    op.create_table(
        "contact_pii",
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name_ciphertext", sa.Text(), nullable=False),
        sa.Column("email_ciphertext", sa.Text(), nullable=True),
        sa.Column("email_blind_index", sa.String(length=128), nullable=True),
        sa.Column("phone_ciphertext", sa.Text(), nullable=True),
        sa.Column("phone_blind_index", sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            "char_length(name_ciphertext) > 0",
            name="ck_contact_pii_name_ciphertext_not_empty",
        ),
        sa.CheckConstraint(
            "(email_ciphertext IS NULL) = (email_blind_index IS NULL)",
            name="ck_contact_pii_email_pair",
        ),
        sa.CheckConstraint(
            "email_ciphertext IS NULL OR char_length(email_ciphertext) > 0",
            name="ck_contact_pii_email_ciphertext_not_empty",
        ),
        sa.CheckConstraint(
            "email_blind_index IS NULL OR char_length(email_blind_index) > 0",
            name="ck_contact_pii_email_blind_index_not_empty",
        ),
        sa.CheckConstraint(
            "(phone_ciphertext IS NULL) = (phone_blind_index IS NULL)",
            name="ck_contact_pii_phone_pair",
        ),
        sa.CheckConstraint(
            "phone_ciphertext IS NULL OR char_length(phone_ciphertext) > 0",
            name="ck_contact_pii_phone_ciphertext_not_empty",
        ),
        sa.CheckConstraint(
            "phone_blind_index IS NULL OR char_length(phone_blind_index) > 0",
            name="ck_contact_pii_phone_blind_index_not_empty",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id", "tenant_id"],
            ["contacts.id", "contacts.tenant_id"],
            name="fk_contact_pii_contact_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("contact_id", name="pk_contact_pii"),
    )
    op.create_index(
        "uq_contact_pii_tenant_email_blind_index",
        "contact_pii",
        ["tenant_id", "email_blind_index"],
        unique=True,
        postgresql_where=sa.text("email_blind_index IS NOT NULL"),
    )
    op.create_index(
        "uq_contact_pii_tenant_phone_blind_index",
        "contact_pii",
        ["tenant_id", "phone_blind_index"],
        unique=True,
        postgresql_where=sa.text("phone_blind_index IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_contact_pii_tenant_phone_blind_index",
        table_name="contact_pii",
    )
    op.drop_index(
        "uq_contact_pii_tenant_email_blind_index",
        table_name="contact_pii",
    )
    op.drop_table("contact_pii")
    op.drop_index("ix_contacts_tenant_listing", table_name="contacts")
    op.drop_table("contacts")
