from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.core.errors import ApplicationError
from app.core.security import (
    AccessTokenClaims,
    AccessTokenCodec,
    InvalidAccessTokenError,
    PasswordManager,
    generate_refresh_token,
    hash_refresh_token,
)
from app.core.tenant_context import TenantContext
from app.integrations.openbao import OpenBaoError
from app.models import RefreshSession
from app.repositories.authentication import AuthenticationIdentity, AuthenticationRepository
from app.services.email_identity import EmailIdentityProtector


@dataclass(frozen=True, slots=True)
class AuthenticationTokens:
    access_token: str
    refresh_token: str
    expires_in: int


@dataclass(frozen=True, slots=True)
class AuthenticatedRole:
    key: str
    name: str


@dataclass(frozen=True, slots=True)
class AuthenticatedAccount:
    user_id: UUID
    email: str
    tenant_id: UUID
    tenant_name: str
    tenant_slug: str
    tenant_user_id: UUID
    joined_at: datetime
    roles: tuple[AuthenticatedRole, ...]
    permissions: tuple[str, ...]


class AuthenticationService:
    def __init__(
        self,
        *,
        repository: AuthenticationRepository,
        email_protector: EmailIdentityProtector,
        password_manager: PasswordManager,
        access_tokens: AccessTokenCodec,
        refresh_token_lifetime: timedelta,
    ) -> None:
        self._repository = repository
        self._email_protector = email_protector
        self._password_manager = password_manager
        self._access_tokens = access_tokens
        self._refresh_token_lifetime = refresh_token_lifetime

    async def login(self, *, email: str, password: str, tenant_slug: str) -> AuthenticationTokens:
        try:
            email_blind_index = await self._email_protector.blind_index(email)
        except OpenBaoError as error:
            raise ApplicationError(
                code="identity_service_unavailable",
                message="The identity service is temporarily unavailable.",
                status_code=503,
            ) from error

        async with self._repository.transaction():
            identity = await self._repository.get_login_identity(
                email_blind_index=email_blind_index,
                tenant_slug=tenant_slug,
            )
            password_hash = identity.user.password_hash if identity else None
            valid, updated_hash = self._password_manager.verify_and_update(password, password_hash)
            if identity is None or not valid:
                raise _invalid_credentials()
            if updated_hash is not None:
                identity.user.password_hash = updated_hash
            return self._issue_tokens(identity)

    async def refresh(self, refresh_token: str) -> AuthenticationTokens:
        token_hash = hash_refresh_token(refresh_token)
        now = datetime.now(UTC)
        tokens: AuthenticationTokens | None = None
        invalid = False

        async with self._repository.transaction():
            identity = await self._repository.get_refresh_identity_for_update(token_hash)
            if identity is None:
                invalid = True
            elif (
                identity.refresh_session.revoked_at is not None
                or identity.refresh_session.expires_at <= now
                or not identity.is_active()
            ):
                await self._repository.revoke_family(identity.refresh_session.family_id, now)
                invalid = True
            else:
                identity.refresh_session.revoked_at = now
                tokens = self._issue_tokens(
                    AuthenticationIdentity(
                        user=identity.user,
                        tenant=identity.tenant,
                        tenant_user=identity.tenant_user,
                    ),
                    family_id=identity.refresh_session.family_id,
                    replaced_session=identity.refresh_session,
                )

        if invalid or tokens is None:
            raise _invalid_refresh_token()
        return tokens

    async def logout(self, refresh_token: str) -> None:
        token_hash = hash_refresh_token(refresh_token)
        now = datetime.now(UTC)
        async with self._repository.transaction():
            identity = await self._repository.get_refresh_identity_for_update(token_hash)
            if identity is not None and identity.refresh_session.revoked_at is None:
                identity.refresh_session.revoked_at = now

    async def authenticate_access_token(self, token: str) -> TenantContext:
        try:
            claims = self._access_tokens.decode(token)
        except InvalidAccessTokenError as error:
            raise _authentication_required() from error

        context = await self._repository.get_active_tenant_context(claims)
        if context is None:
            raise _authentication_required()
        return context

    async def get_authenticated_account(
        self,
        context: TenantContext,
    ) -> AuthenticatedAccount:
        identity = await self._repository.get_authenticated_identity(context)
        if identity is None:
            raise _authentication_required()
        try:
            email = await self._email_protector.reveal(
                identity.user.id,
                identity.user.email_ciphertext,
            )
        except (OpenBaoError, UnicodeDecodeError) as error:
            raise ApplicationError(
                code="identity_service_unavailable",
                message="The identity service is temporarily unavailable.",
                status_code=503,
            ) from error

        roles = await self._repository.get_active_roles(
            tenant_id=context.tenant_id,
            tenant_user_id=context.tenant_user_id,
        )
        return AuthenticatedAccount(
            user_id=identity.user.id,
            email=email,
            tenant_id=identity.tenant.id,
            tenant_name=identity.tenant.name,
            tenant_slug=identity.tenant.slug,
            tenant_user_id=identity.tenant_user.id,
            joined_at=identity.tenant_user.joined_at,
            roles=tuple(AuthenticatedRole(key=role.key, name=role.name) for role in roles),
            permissions=tuple(sorted(context.permissions)),
        )

    async def change_password(
        self,
        *,
        context: TenantContext,
        current_password: str,
        new_password: str,
    ) -> None:
        now = datetime.now(UTC)
        async with self._repository.transaction():
            identity = await self._repository.get_authenticated_identity_for_update(context)
            if identity is None:
                raise _authentication_required()
            valid, _ = self._password_manager.verify_and_update(
                current_password,
                identity.user.password_hash,
            )
            if not valid:
                raise ApplicationError(
                    code="invalid_current_password",
                    message="The current password is invalid.",
                    status_code=400,
                )
            identity.user.password_hash = self._password_manager.hash(new_password)
            await self._repository.revoke_user_sessions(identity.user.id, now)

    def _issue_tokens(
        self,
        identity: AuthenticationIdentity,
        *,
        family_id: UUID | None = None,
        replaced_session: RefreshSession | None = None,
    ) -> AuthenticationTokens:
        refresh_token = generate_refresh_token()
        refresh_session = RefreshSession(
            id=uuid4(),
            family_id=family_id or uuid4(),
            user_id=identity.user.id,
            tenant_user_id=identity.tenant_user.id,
            token_hash=refresh_token.digest,
            expires_at=datetime.now(UTC) + self._refresh_token_lifetime,
        )
        self._repository.add_refresh_session(refresh_session)
        if replaced_session is not None:
            replaced_session.replaced_by_id = refresh_session.id

        access_token = self._access_tokens.encode(
            AccessTokenClaims(
                user_id=identity.user.id,
                tenant_id=identity.tenant.id,
                tenant_user_id=identity.tenant_user.id,
            )
        )
        return AuthenticationTokens(
            access_token=access_token,
            refresh_token=refresh_token.plaintext,
            expires_in=self._access_tokens.expires_in_seconds,
        )


def _invalid_credentials() -> ApplicationError:
    return ApplicationError(
        code="invalid_credentials",
        message="Invalid credentials.",
        status_code=401,
    )


def _invalid_refresh_token() -> ApplicationError:
    return ApplicationError(
        code="invalid_refresh_token",
        message="The refresh token is invalid or expired.",
        status_code=401,
    )


def _authentication_required() -> ApplicationError:
    return ApplicationError(
        code="authentication_required",
        message="Authentication is required.",
        status_code=401,
    )
