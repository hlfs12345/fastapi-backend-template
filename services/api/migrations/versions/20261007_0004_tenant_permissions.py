"""Add tenant administration permissions.

Revision ID: 20261007_0004
Revises: 20260928_0003
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261007_0004"
down_revision: str | None = "20260928_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PERMISSIONS = (
    ("tenant.view", "View tenant details."),
    ("tenant.manage", "Manage tenant details."),
)


def upgrade() -> None:
    permissions = sa.table(
        "permissions",
        sa.column("code", sa.String(length=100)),
        sa.column("description", sa.String(length=255)),
    )
    op.bulk_insert(
        permissions,
        [{"code": code, "description": description} for code, description in _PERMISSIONS],
    )
    op.execute(
        sa.text(
            """
            INSERT INTO role_permissions (tenant_id, role_id, permission_code)
            SELECT roles.tenant_id, roles.id, permissions.code
            FROM roles
            CROSS JOIN permissions
            WHERE roles.key = 'owner'
              AND roles.is_system = true
              AND permissions.code IN ('tenant.view', 'tenant.manage')
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM role_permissions
            WHERE permission_code IN ('tenant.view', 'tenant.manage')
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM permissions
            WHERE code IN ('tenant.view', 'tenant.manage')
            """
        )
    )
