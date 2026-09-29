from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_role_service, get_tenant_context
from app.core.config import Settings
from app.core.permissions import ROLES_MANAGE
from app.core.tenant_context import TenantContext
from app.main import create_app
from app.services.roles import RoleDetails, RoleService


def test_roles_endpoint_denies_context_without_permission(settings: Settings) -> None:
    app = create_app(settings)
    context = TenantContext(
        tenant_id=uuid4(),
        user_id=uuid4(),
        tenant_user_id=uuid4(),
    )
    service = AsyncMock(spec=RoleService)
    app.dependency_overrides[get_tenant_context] = lambda: context
    app.dependency_overrides[get_role_service] = lambda: service

    with TestClient(app) as client:
        response = client.get("/roles")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"
    service.list_roles.assert_not_awaited()


def test_create_role_uses_authenticated_tenant_context(settings: Settings) -> None:
    app = create_app(settings)
    context = TenantContext(
        tenant_id=uuid4(),
        user_id=uuid4(),
        tenant_user_id=uuid4(),
        permissions=frozenset({ROLES_MANAGE}),
    )
    role = RoleDetails(
        id=uuid4(),
        tenant_id=context.tenant_id,
        key="sales",
        name="Sales",
        description=None,
        is_system=False,
        permission_codes=("contacts.view",),
    )
    service = AsyncMock(spec=RoleService)
    service.create_role.return_value = role
    app.dependency_overrides[get_tenant_context] = lambda: context
    app.dependency_overrides[get_role_service] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            "/roles",
            json={
                "key": "sales",
                "name": "Sales",
                "permission_codes": ["contacts.view"],
            },
            headers={"X-Tenant-ID": str(uuid4())},
        )

    assert response.status_code == 201
    assert response.json()["tenant_id"] == str(context.tenant_id)
    service.create_role.assert_awaited_once_with(
        context=context,
        key="sales",
        name="Sales",
        description=None,
        permission_codes=frozenset({"contacts.view"}),
    )
