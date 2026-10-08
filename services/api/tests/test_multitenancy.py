from typing import Annotated
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

from app.api.dependencies import get_tenant_context
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.tenant_context import TenantContext
from app.main import create_app
from app.models import RefreshSession, Tenant, TenantUser, User, metadata
from app.services.authentication import AuthenticationService


def test_multitenant_tables_are_registered_for_migrations() -> None:
    assert set(metadata.tables) == {
        "legal_acceptances",
        "legal_document_versions",
        "legal_documents",
        "permissions",
        "refresh_sessions",
        "role_permissions",
        "roles",
        "tenants",
        "tenant_user_roles",
        "users",
        "tenant_users",
    }


def test_users_are_global_and_memberships_link_users_to_tenants() -> None:
    assert "tenant_id" not in User.__table__.columns
    assert {column.name for column in TenantUser.__table__.columns} >= {
        "tenant_id",
        "user_id",
        "deactivated_at",
    }

    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in TenantUser.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("tenant_id", "user_id") in unique_columns
    assert ("user_id",) not in unique_columns
    assert ("tenant_id",) not in unique_columns


def test_role_assignments_enforce_same_tenant_in_database_metadata() -> None:
    assignment_table = metadata.tables["tenant_user_roles"]
    composite_foreign_keys = {
        (
            tuple(column.name for column in constraint.columns),
            tuple(element.target_fullname for element in constraint.elements),
        )
        for constraint in assignment_table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    assert (
        ("tenant_user_id", "tenant_id"),
        ("tenant_users.id", "tenant_users.tenant_id"),
    ) in composite_foreign_keys
    assert (
        ("role_id", "tenant_id"),
        ("roles.id", "roles.tenant_id"),
    ) in composite_foreign_keys


def test_tenants_and_memberships_support_deactivation_without_deletion() -> None:
    assert "deactivated_at" in Tenant.__table__.columns
    assert "deactivated_at" in TenantUser.__table__.columns
    assert "disabled_at" in User.__table__.columns


def test_authentication_storage_excludes_plaintext_identity_and_tokens() -> None:
    assert "email" not in User.__table__.columns
    assert {"email_ciphertext", "email_blind_index", "password_hash"} <= set(
        User.__table__.columns.keys()
    )
    assert "refresh_token" not in RefreshSession.__table__.columns
    assert "token_hash" in RefreshSession.__table__.columns


def test_client_cannot_select_tenant_from_header_or_query(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/_test/tenant-context")
    def read_context(
        context: Annotated[TenantContext, Depends(get_tenant_context)],
    ) -> dict[str, str]:
        return {"tenant_id": str(context.tenant_id)}

    supplied_tenant_id = uuid4()
    with TestClient(app) as client:
        response = client.get(
            f"/_test/tenant-context?tenant_id={supplied_tenant_id}",
            headers={"X-Tenant-ID": str(supplied_tenant_id)},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


@pytest.mark.asyncio
async def test_tenant_context_rejects_missing_bearer_token() -> None:
    request = Request({"type": "http"})
    service = AsyncMock(spec=AuthenticationService)
    service.authenticate_access_token.side_effect = ApplicationError(
        code="authentication_required",
        message="Authentication is required.",
        status_code=401,
    )

    with pytest.raises(ApplicationError) as raised:
        await get_tenant_context(request, None, service)

    assert raised.value.code == "authentication_required"
    service.authenticate_access_token.assert_awaited_once_with("")


@pytest.mark.asyncio
async def test_tenant_context_comes_from_validated_access_token() -> None:
    expected_context = TenantContext(
        tenant_id=uuid4(),
        user_id=uuid4(),
        tenant_user_id=uuid4(),
    )
    request = Request({"type": "http"})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="signed-token")
    service = AsyncMock(spec=AuthenticationService)
    service.authenticate_access_token.return_value = expected_context

    assert await get_tenant_context(request, credentials, service) is expected_context
    assert request.state.tenant_context is expected_context
