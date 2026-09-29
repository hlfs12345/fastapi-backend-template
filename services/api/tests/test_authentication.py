from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.errors import ApplicationError
from app.core.security import AccessTokenCodec, PasswordManager
from app.core.tenant_context import TenantContext
from app.models import RefreshSession, Tenant, TenantUser, User
from app.repositories.authentication import AuthenticationIdentity, RefreshIdentity
from app.services.authentication import AuthenticationService
from app.services.email_identity import EmailIdentityProtector


class FakeAuthenticationRepository:
    def __init__(self) -> None:
        self.login_identity: AuthenticationIdentity | None = None
        self.refresh_identity: RefreshIdentity | None = None
        self.active_context: TenantContext | None = None
        self.refresh_sessions: list[RefreshSession] = []
        self.revoked_families: list[object] = []

    @asynccontextmanager
    async def transaction(self):
        yield

    async def get_login_identity(self, **kwargs) -> AuthenticationIdentity | None:
        return self.login_identity

    async def get_active_tenant_context(self, claims) -> TenantContext | None:
        return self.active_context

    async def get_refresh_identity_for_update(self, token_hash: bytes) -> RefreshIdentity | None:
        return self.refresh_identity

    def add_refresh_session(self, refresh_session: RefreshSession) -> None:
        self.refresh_sessions.append(refresh_session)

    async def revoke_family(self, family_id, revoked_at: datetime) -> None:
        self.revoked_families.append(family_id)


def _identity(password_hash: str) -> AuthenticationIdentity:
    tenant = Tenant(id=uuid4(), name="Tenant", slug="tenant")
    user = User(
        id=uuid4(),
        email_ciphertext="vault:v1:ciphertext",
        email_blind_index="vault:v1:hmac",
        password_hash=password_hash,
    )
    tenant_user = TenantUser(id=uuid4(), tenant_id=tenant.id, user_id=user.id)
    return AuthenticationIdentity(user=user, tenant=tenant, tenant_user=tenant_user)


def _service(
    repository: FakeAuthenticationRepository,
    password_manager: PasswordManager,
) -> AuthenticationService:
    email_protector = AsyncMock(spec=EmailIdentityProtector)
    email_protector.blind_index.return_value = "vault:v1:hmac"
    return AuthenticationService(
        repository=repository,  # type: ignore[arg-type]
        email_protector=email_protector,
        password_manager=password_manager,
        access_tokens=AccessTokenCodec(
            secret="test-only-jwt-secret-with-at-least-32-characters",
            issuer="edisk-api",
            audience="edisk-app",
            lifetime=timedelta(minutes=15),
        ),
        refresh_token_lifetime=timedelta(days=30),
    )


@pytest.mark.asyncio
async def test_login_issues_tenant_bound_access_and_hashed_refresh_session() -> None:
    repository = FakeAuthenticationRepository()
    passwords = PasswordManager()
    identity = _identity(passwords.hash("correct password"))
    repository.login_identity = identity
    service = _service(repository, passwords)

    tokens = await service.login(
        email="user@example.com",
        password="correct password",
        tenant_slug="tenant",
    )

    assert tokens.access_token
    assert tokens.refresh_token
    assert len(repository.refresh_sessions) == 1
    refresh_session = repository.refresh_sessions[0]
    assert refresh_session.token_hash != tokens.refresh_token.encode()
    assert refresh_session.user_id == identity.user.id
    assert refresh_session.tenant_user_id == identity.tenant_user.id


@pytest.mark.asyncio
async def test_login_uses_same_error_for_unknown_user_and_wrong_password() -> None:
    passwords = PasswordManager()
    for identity in (None, _identity(passwords.hash("correct password"))):
        repository = FakeAuthenticationRepository()
        repository.login_identity = identity
        service = _service(repository, passwords)

        with pytest.raises(ApplicationError) as raised:
            await service.login(
                email="user@example.com",
                password="wrong password",
                tenant_slug="tenant",
            )

        assert raised.value.code == "invalid_credentials"


@pytest.mark.asyncio
async def test_refresh_rotates_token_and_links_replacement() -> None:
    repository = FakeAuthenticationRepository()
    passwords = PasswordManager()
    identity = _identity(passwords.hash("correct password"))
    current_session = RefreshSession(
        id=uuid4(),
        family_id=uuid4(),
        user_id=identity.user.id,
        tenant_user_id=identity.tenant_user.id,
        token_hash=b"x" * 32,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    repository.refresh_identity = RefreshIdentity(
        refresh_session=current_session,
        user=identity.user,
        tenant=identity.tenant,
        tenant_user=identity.tenant_user,
    )
    service = _service(repository, passwords)

    tokens = await service.refresh("a-valid-looking-refresh-token" * 3)

    replacement = repository.refresh_sessions[0]
    assert tokens.refresh_token
    assert current_session.revoked_at is not None
    assert current_session.replaced_by_id == replacement.id
    assert replacement.family_id == current_session.family_id


@pytest.mark.asyncio
async def test_reused_refresh_token_revokes_its_family() -> None:
    repository = FakeAuthenticationRepository()
    passwords = PasswordManager()
    identity = _identity(passwords.hash("correct password"))
    reused_session = RefreshSession(
        id=uuid4(),
        family_id=uuid4(),
        user_id=identity.user.id,
        tenant_user_id=identity.tenant_user.id,
        token_hash=b"x" * 32,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        revoked_at=datetime.now(UTC),
    )
    repository.refresh_identity = RefreshIdentity(
        refresh_session=reused_session,
        user=identity.user,
        tenant=identity.tenant,
        tenant_user=identity.tenant_user,
    )
    service = _service(repository, passwords)

    with pytest.raises(ApplicationError) as raised:
        await service.refresh("a-reused-refresh-token" * 4)

    assert raised.value.code == "invalid_refresh_token"
    assert repository.revoked_families == [reused_session.family_id]


@pytest.mark.asyncio
async def test_access_token_requires_current_active_membership() -> None:
    repository = FakeAuthenticationRepository()
    passwords = PasswordManager()
    identity = _identity(passwords.hash("correct password"))
    service = _service(repository, passwords)
    repository.login_identity = identity
    issued = await service.login(
        email="user@example.com",
        password="correct password",
        tenant_slug="tenant",
    )

    with pytest.raises(ApplicationError) as raised:
        await service.authenticate_access_token(issued.access_token)
    assert raised.value.code == "authentication_required"

    expected_context = TenantContext(
        user_id=identity.user.id,
        tenant_id=identity.tenant.id,
        tenant_user_id=identity.tenant_user.id,
    )
    repository.active_context = expected_context
    assert await service.authenticate_access_token(issued.access_token) == expected_context
