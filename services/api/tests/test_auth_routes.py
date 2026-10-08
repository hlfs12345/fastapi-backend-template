from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_authentication_service, get_tenant_context
from app.core.config import Settings
from app.core.tenant_context import TenantContext
from app.main import create_app
from app.services.authentication import (
    AuthenticatedAccount,
    AuthenticatedRole,
    AuthenticationService,
    AuthenticationTokens,
)


def test_api_fails_closed_without_jwt_secret() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://test:test@127.0.0.1:5432/test",
        redis_url="redis://127.0.0.1:6379/0",
        openbao_url="http://127.0.0.1:8200",
    )
    app = create_app(settings)

    with pytest.raises(RuntimeError, match="EDISK_AUTH_JWT_SECRET"):
        with TestClient(app):
            pass


def test_login_returns_access_and_refresh_tokens(settings: Settings) -> None:
    app = create_app(settings)
    service = AsyncMock(spec=AuthenticationService)
    service.login.return_value = AuthenticationTokens(
        access_token="access-token",
        refresh_token="refresh-token",
        expires_in=900,
    )
    app.dependency_overrides[get_authentication_service] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            "/auth/login",
            json={
                "email": "user@example.com",
                "password": "not-logged-password",
                "tenant_slug": "tenant",
            },
        )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"
    assert response.json() == {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "token_type": "bearer",
        "expires_in": 900,
    }
    service.login.assert_awaited_once_with(
        email="user@example.com",
        password="not-logged-password",
        tenant_slug="tenant",
    )


def test_me_returns_authenticated_account_context(settings: Settings) -> None:
    app = create_app(settings)
    context = TenantContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        tenant_user_id=uuid4(),
        permissions=frozenset({"users.view", "contacts.view"}),
    )
    joined_at = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)
    service = AsyncMock(spec=AuthenticationService)
    service.get_authenticated_account.return_value = AuthenticatedAccount(
        user_id=context.user_id,
        email="user@example.com",
        tenant_id=context.tenant_id,
        tenant_name="Tenant",
        tenant_slug="tenant",
        tenant_user_id=context.tenant_user_id,
        joined_at=joined_at,
        roles=(AuthenticatedRole(key="owner", name="Owner"),),
        permissions=("contacts.view", "users.view"),
    )
    app.dependency_overrides[get_tenant_context] = lambda: context
    app.dependency_overrides[get_authentication_service] = lambda: service

    with TestClient(app) as client:
        response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {
        "user_id": str(context.user_id),
        "email": "user@example.com",
        "tenant_id": str(context.tenant_id),
        "tenant_name": "Tenant",
        "tenant_slug": "tenant",
        "tenant_user_id": str(context.tenant_user_id),
        "joined_at": "2026-01-02T03:04:00Z",
        "roles": [{"key": "owner", "name": "Owner"}],
        "permissions": ["contacts.view", "users.view"],
    }
    service.get_authenticated_account.assert_awaited_once_with(context)


def test_refresh_rotates_and_logout_revokes_through_service(settings: Settings) -> None:
    app = create_app(settings)
    service = AsyncMock(spec=AuthenticationService)
    service.refresh.return_value = AuthenticationTokens(
        access_token="rotated-access-token",
        refresh_token="rotated-refresh-token",
        expires_in=900,
    )
    app.dependency_overrides[get_authentication_service] = lambda: service
    supplied_token = "r" * 86

    with TestClient(app) as client:
        refresh_response = client.post(
            "/auth/refresh",
            json={"refresh_token": supplied_token},
        )
        logout_response = client.post(
            "/auth/logout",
            json={"refresh_token": supplied_token},
        )

    assert refresh_response.status_code == 200
    assert refresh_response.headers["Cache-Control"] == "no-store"
    assert refresh_response.json()["refresh_token"] == "rotated-refresh-token"
    assert logout_response.status_code == 204
    assert not logout_response.content
    service.refresh.assert_awaited_once_with(supplied_token)
    service.logout.assert_awaited_once_with(supplied_token)
