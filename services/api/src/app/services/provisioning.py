import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.exc import IntegrityError

from app.core.errors import ApplicationError
from app.core.permissions import ALL_PERMISSION_CODES
from app.core.security import PasswordManager
from app.integrations.openbao import OpenBaoError
from app.models import Role, RolePermission, Tenant, TenantUser, TenantUserRole, User
from app.repositories.provisioning import ProvisioningRepository
from app.services.email_identity import EmailIdentityProtector

_EMAIL_ADAPTER = TypeAdapter(EmailStr)
_TENANT_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class ProvisionedTenant:
    tenant_id: UUID
    user_id: UUID
    tenant_user_id: UUID
    owner_role_id: UUID
    reused_user: bool


class TenantProvisioningService:
    def __init__(
        self,
        *,
        repository: ProvisioningRepository,
        email_protector: EmailIdentityProtector,
        password_manager: PasswordManager,
    ) -> None:
        self._repository = repository
        self._email_protector = email_protector
        self._password_manager = password_manager

    async def provision(
        self,
        *,
        tenant_name: str,
        tenant_slug: str,
        email: str,
        password: str,
    ) -> ProvisionedTenant:
        normalized_name, normalized_slug, validated_email = _validate_input(
            tenant_name=tenant_name,
            tenant_slug=tenant_slug,
            email=email,
            password=password,
        )
        candidate_user_id = uuid4()
        try:
            protected_email = await self._email_protector.protect(
                candidate_user_id, validated_email
            )
        except OpenBaoError as error:
            raise ApplicationError(
                code="identity_service_unavailable",
                message="The identity service is temporarily unavailable.",
                status_code=503,
            ) from error
        candidate_password_hash = self._password_manager.hash(password)

        try:
            async with self._repository.transaction():
                if await self._repository.get_tenant_by_slug(normalized_slug) is not None:
                    raise _provisioning_conflict()

                user = await self._repository.get_user_by_email_blind_index_for_update(
                    protected_email.blind_index
                )
                reused_user = user is not None
                if user is None:
                    user = User(
                        id=candidate_user_id,
                        email_ciphertext=protected_email.ciphertext,
                        email_blind_index=protected_email.blind_index,
                        password_hash=candidate_password_hash,
                    )
                    self._repository.add_user(user)
                else:
                    if user.disabled_at is not None:
                        raise _user_unavailable()
                    valid, updated_hash = self._password_manager.verify_and_update(
                        password,
                        user.password_hash,
                    )
                    if not valid:
                        raise _existing_identity_mismatch()
                    if updated_hash is not None:
                        user.password_hash = updated_hash

                tenant = Tenant(id=uuid4(), name=normalized_name, slug=normalized_slug)
                membership = TenantUser(
                    id=uuid4(),
                    tenant_id=tenant.id,
                    user_id=user.id,
                )
                owner_role = Role(
                    id=uuid4(),
                    tenant_id=tenant.id,
                    key="owner",
                    name="Owner",
                    description="Tenant owner with all available permissions.",
                    is_system=True,
                )
                self._repository.add_tenant(tenant)
                self._repository.add_membership(membership)
                self._repository.add_role(owner_role)
                for permission_code in sorted(ALL_PERMISSION_CODES):
                    self._repository.add_role_permission(
                        RolePermission(
                            tenant_id=tenant.id,
                            role_id=owner_role.id,
                            permission_code=permission_code,
                        )
                    )
                self._repository.add_tenant_user_role(
                    TenantUserRole(
                        tenant_id=tenant.id,
                        tenant_user_id=membership.id,
                        role_id=owner_role.id,
                        assigned_by_tenant_user_id=membership.id,
                    )
                )
                await self._repository.flush()

                return ProvisionedTenant(
                    tenant_id=tenant.id,
                    user_id=user.id,
                    tenant_user_id=membership.id,
                    owner_role_id=owner_role.id,
                    reused_user=reused_user,
                )
        except IntegrityError as error:
            raise _provisioning_conflict() from error


def _validate_input(
    *,
    tenant_name: str,
    tenant_slug: str,
    email: str,
    password: str,
) -> tuple[str, str, str]:
    normalized_name = tenant_name.strip()
    normalized_slug = tenant_slug.strip()
    if not normalized_name or len(normalized_name) > 200:
        raise _invalid_provisioning_input()
    if not 3 <= len(normalized_slug) <= 63 or not _TENANT_SLUG_PATTERN.fullmatch(normalized_slug):
        raise _invalid_provisioning_input()
    if not 12 <= len(password) <= 1024:
        raise _invalid_provisioning_input()
    try:
        validated_email = str(_EMAIL_ADAPTER.validate_python(email))
    except ValidationError as error:
        raise _invalid_provisioning_input() from error
    return normalized_name, normalized_slug, validated_email


def _invalid_provisioning_input() -> ApplicationError:
    return ApplicationError(
        code="invalid_provisioning_input",
        message="The provisioning data is invalid.",
        status_code=422,
    )


def _provisioning_conflict() -> ApplicationError:
    return ApplicationError(
        code="provisioning_conflict",
        message="The tenant or identity cannot be provisioned.",
        status_code=409,
    )


def _existing_identity_mismatch() -> ApplicationError:
    return ApplicationError(
        code="existing_identity_mismatch",
        message="The existing identity could not be verified.",
        status_code=409,
    )


def _user_unavailable() -> ApplicationError:
    return ApplicationError(
        code="user_unavailable",
        message="The existing identity is unavailable.",
        status_code=409,
    )
