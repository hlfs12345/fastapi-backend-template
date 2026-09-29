from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.errors import ApplicationError
from app.core.permissions import ALL_PERMISSION_CODES
from app.core.security import PasswordManager
from app.models import Role, RolePermission, Tenant, TenantUser, TenantUserRole, User
from app.services.email_identity import EmailIdentityProtector, ProtectedEmail
from app.services.provisioning import TenantProvisioningService


class FakeProvisioningRepository:
    def __init__(self) -> None:
        self.existing_tenant: Tenant | None = None
        self.existing_user: User | None = None
        self.added_tenants: list[Tenant] = []
        self.added_users: list[User] = []
        self.added_memberships: list[TenantUser] = []
        self.added_roles: list[Role] = []
        self.added_role_permissions: list[RolePermission] = []
        self.added_tenant_user_roles: list[TenantUserRole] = []
        self.flush_count = 0

    @asynccontextmanager
    async def transaction(self):
        yield

    async def get_tenant_by_slug(self, slug: str) -> Tenant | None:
        return self.existing_tenant

    async def get_user_by_email_blind_index_for_update(self, blind_index: str) -> User | None:
        return self.existing_user

    def add_tenant(self, tenant: Tenant) -> None:
        self.added_tenants.append(tenant)

    def add_user(self, user: User) -> None:
        self.added_users.append(user)

    def add_membership(self, membership: TenantUser) -> None:
        self.added_memberships.append(membership)

    def add_role(self, role: Role) -> None:
        self.added_roles.append(role)

    def add_role_permission(self, role_permission: RolePermission) -> None:
        self.added_role_permissions.append(role_permission)

    def add_tenant_user_role(self, tenant_user_role: TenantUserRole) -> None:
        self.added_tenant_user_roles.append(tenant_user_role)

    async def flush(self) -> None:
        self.flush_count += 1


def _service(
    repository: FakeProvisioningRepository,
) -> tuple[TenantProvisioningService, AsyncMock, MagicMock]:
    email_protector = AsyncMock(spec=EmailIdentityProtector)
    email_protector.protect.return_value = ProtectedEmail(
        ciphertext="vault:v1:ciphertext",
        blind_index="vault:v1:hmac",
    )
    passwords = MagicMock(spec=PasswordManager)
    passwords.hash.return_value = "$argon2id$protected"
    service = TenantProvisioningService(
        repository=repository,  # type: ignore[arg-type]
        email_protector=email_protector,
        password_manager=passwords,
    )
    return service, email_protector, passwords


@pytest.mark.asyncio
async def test_provisioning_creates_tenant_global_user_and_membership() -> None:
    repository = FakeProvisioningRepository()
    service, email_protector, passwords = _service(repository)

    result = await service.provision(
        tenant_name="  Example Tenant  ",
        tenant_slug="example-tenant",
        email="USER@example.com",
        password="correct password",
    )

    assert not result.reused_user
    assert repository.flush_count == 1
    assert len(repository.added_tenants) == 1
    assert len(repository.added_users) == 1
    assert len(repository.added_memberships) == 1
    assert len(repository.added_roles) == 1
    tenant = repository.added_tenants[0]
    user = repository.added_users[0]
    membership = repository.added_memberships[0]
    assert tenant.name == "Example Tenant"
    assert user.email_ciphertext == "vault:v1:ciphertext"
    assert user.email_blind_index == "vault:v1:hmac"
    assert user.password_hash == "$argon2id$protected"
    assert membership.tenant_id == tenant.id == result.tenant_id
    assert membership.user_id == user.id == result.user_id
    assert membership.id == result.tenant_user_id
    owner_role = repository.added_roles[0]
    assert owner_role.id == result.owner_role_id
    assert owner_role.tenant_id == tenant.id
    assert owner_role.key == "owner"
    assert owner_role.is_system
    assert {item.permission_code for item in repository.added_role_permissions} == set(
        ALL_PERMISSION_CODES
    )
    assert len(repository.added_tenant_user_roles) == 1
    owner_assignment = repository.added_tenant_user_roles[0]
    assert owner_assignment.tenant_id == tenant.id
    assert owner_assignment.tenant_user_id == membership.id
    assert owner_assignment.role_id == owner_role.id
    assert owner_assignment.assigned_by_tenant_user_id == membership.id
    email_protector.protect.assert_awaited_once()
    passwords.hash.assert_called_once_with("correct password")


@pytest.mark.asyncio
async def test_provisioning_reuses_verified_global_user_for_another_tenant() -> None:
    repository = FakeProvisioningRepository()
    existing_user = User(
        id=uuid4(),
        email_ciphertext="vault:v1:existing",
        email_blind_index="vault:v1:hmac",
        password_hash="$argon2id$existing",
    )
    repository.existing_user = existing_user
    service, _, passwords = _service(repository)
    passwords.verify_and_update.return_value = (True, "$argon2id$updated")

    result = await service.provision(
        tenant_name="Second Tenant",
        tenant_slug="second-tenant",
        email="user@example.com",
        password="correct password",
    )

    assert result.reused_user
    assert result.user_id == existing_user.id
    assert not repository.added_users
    assert repository.added_memberships[0].user_id == existing_user.id
    assert existing_user.password_hash == "$argon2id$updated"
    passwords.verify_and_update.assert_called_once_with(
        "correct password",
        "$argon2id$existing",
    )


@pytest.mark.asyncio
async def test_provisioning_rejects_password_mismatch_for_existing_identity() -> None:
    repository = FakeProvisioningRepository()
    repository.existing_user = User(
        id=uuid4(),
        email_ciphertext="vault:v1:existing",
        email_blind_index="vault:v1:hmac",
        password_hash="$argon2id$existing",
    )
    service, _, passwords = _service(repository)
    passwords.verify_and_update.return_value = (False, None)

    with pytest.raises(ApplicationError) as raised:
        await service.provision(
            tenant_name="Second Tenant",
            tenant_slug="second-tenant",
            email="user@example.com",
            password="wrong password",
        )

    assert raised.value.code == "existing_identity_mismatch"
    assert not repository.added_tenants
    assert not repository.added_memberships


@pytest.mark.asyncio
async def test_provisioning_rejects_duplicate_tenant_slug() -> None:
    repository = FakeProvisioningRepository()
    repository.existing_tenant = Tenant(id=uuid4(), name="Existing", slug="existing")
    service, _, _ = _service(repository)

    with pytest.raises(ApplicationError) as raised:
        await service.provision(
            tenant_name="Existing",
            tenant_slug="existing",
            email="user@example.com",
            password="correct password",
        )

    assert raised.value.code == "provisioning_conflict"
    assert not repository.added_users
    assert not repository.added_tenants


@pytest.mark.asyncio
async def test_provisioning_rejects_invalid_input_before_protecting_identity() -> None:
    repository = FakeProvisioningRepository()
    service, email_protector, passwords = _service(repository)

    with pytest.raises(ApplicationError) as raised:
        await service.provision(
            tenant_name="Tenant",
            tenant_slug="INVALID SLUG",
            email="not-an-email",
            password="short",
        )

    assert raised.value.code == "invalid_provisioning_input"
    email_protector.protect.assert_not_awaited()
    passwords.hash.assert_not_called()
