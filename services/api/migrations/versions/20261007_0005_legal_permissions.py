"""Add legal document permissions.

Revision ID: 20261007_0005
Revises: 20261007_0004
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261007_0005"
down_revision: str | None = "20261007_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PERMISSIONS = (
    ("legal.publish", "Create legal documents and publish new versions."),
    ("legal.accept_for_tenant", "Accept legal documents on behalf of the tenant."),
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
              AND permissions.code IN ('legal.publish', 'legal.accept_for_tenant')
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM role_permissions
            WHERE permission_code IN ('legal.publish', 'legal.accept_for_tenant')
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM permissions
            WHERE code IN ('legal.publish', 'legal.accept_for_tenant')
            """
        )
    )
