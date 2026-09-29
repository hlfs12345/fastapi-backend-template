"""Add tenant-scoped roles and semantic permissions.

Revision ID: 20260928_0003
Revises: 20260928_0002
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260928_0003"
down_revision: str | None = "20260928_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PERMISSIONS = (
    ("roles.view", "View roles and their permissions."),
    ("roles.manage", "Create and update roles and role assignments."),
    ("users.view", "View tenant users."),
    ("users.manage", "Manage tenant users."),
    ("contacts.view", "View contacts."),
    ("contacts.edit", "Create and update contacts."),
    ("contacts.export", "Export contact data."),
    ("contacts.view_sensitive", "View sensitive contact data."),
    ("campaigns.create", "Create and update campaigns."),
    ("campaigns.send", "Start campaign sends."),
    ("stock.view", "View inventory."),
    ("stock.adjust", "Adjust inventory quantities."),
    ("tracking.view", "View tracked assets and positions."),
    ("tracking.manage", "Manage trackers and assignments."),
)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_tenant_users_id_tenant_id",
        "tenant_users",
        ["id", "tenant_id"],
    )
    permissions = op.create_table(
        "permissions",
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_permissions"),
    )
    op.bulk_insert(
        permissions,
        [{"code": code, "description": description} for code, description in _PERMISSIONS],
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=63), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column(
            "is_system",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
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
            "char_length(btrim(name)) > 0",
            name="ck_roles_name_not_blank",
        ),
        sa.CheckConstraint(
            "char_length(key) BETWEEN 1 AND 63",
            name="ck_roles_key_length",
        ),
        sa.CheckConstraint("key = lower(key)", name="ck_roles_key_lowercase"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_roles_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
        sa.UniqueConstraint("id", "tenant_id", name="uq_roles_id_tenant_id"),
        sa.UniqueConstraint("tenant_id", "key", name="uq_roles_tenant_id_key"),
    )
    op.create_table(
        "role_permissions",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_code", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_code"],
            ["permissions.code"],
            name="fk_role_permissions_permission_code_permissions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["role_id", "tenant_id"],
            ["roles.id", "roles.tenant_id"],
            name="fk_role_permissions_role_tenant_roles",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "role_id",
            "permission_code",
            name="pk_role_permissions",
        ),
    )
    op.create_table(
        "tenant_user_roles",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_by_tenant_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_tenant_user_id", "tenant_id"],
            ["tenant_users.id", "tenant_users.tenant_id"],
            name="fk_tenant_user_roles_assigner_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_user_id", "tenant_id"],
            ["tenant_users.id", "tenant_users.tenant_id"],
            name="fk_tenant_user_roles_member_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id", "tenant_id"],
            ["roles.id", "roles.tenant_id"],
            name="fk_tenant_user_roles_role_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "tenant_user_id",
            "role_id",
            name="pk_tenant_user_roles",
        ),
    )
    op.create_index(
        "ix_tenant_user_roles_role",
        "tenant_user_roles",
        ["tenant_id", "role_id"],
    )
    op.execute(
        sa.text(
            """
            INSERT INTO roles (
                id, tenant_id, key, name, description, is_system
            )
            SELECT
                gen_random_uuid(), id, 'owner', 'Owner',
                'Tenant owner with all available permissions.', true
            FROM tenants
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO role_permissions (tenant_id, role_id, permission_code)
            SELECT roles.tenant_id, roles.id, permissions.code
            FROM roles
            CROSS JOIN permissions
            WHERE roles.key = 'owner' AND roles.is_system = true
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO tenant_user_roles (
                tenant_id, tenant_user_id, role_id, assigned_by_tenant_user_id
            )
            SELECT
                roles.tenant_id,
                first_member.id,
                roles.id,
                first_member.id
            FROM roles
            JOIN LATERAL (
                SELECT tenant_users.id
                FROM tenant_users
                WHERE tenant_users.tenant_id = roles.tenant_id
                  AND tenant_users.deactivated_at IS NULL
                ORDER BY tenant_users.joined_at, tenant_users.id
                LIMIT 1
            ) AS first_member ON true
            WHERE roles.key = 'owner' AND roles.is_system = true
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_user_roles_role", table_name="tenant_user_roles")
    op.drop_table("tenant_user_roles")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("permissions")
    op.drop_constraint(
        "uq_tenant_users_id_tenant_id",
        "tenant_users",
        type_="unique",
    )
