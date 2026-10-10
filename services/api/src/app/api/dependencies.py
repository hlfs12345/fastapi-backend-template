from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApplicationError
from app.core.tenant_context import TenantContext
from app.db.database import Database
from app.repositories.authentication import AuthenticationRepository
from app.repositories.contacts import ContactRepository
from app.repositories.legal import LegalRepository
from app.repositories.roles import RoleRepository
from app.repositories.tenants import TenantRepository
from app.repositories.users import UserRepository
from app.services.authentication import AuthenticationService
from app.services.contact_data_protection import ContactDataProtector
from app.services.contacts import ContactService
from app.services.email_identity import EmailIdentityProtector
from app.services.legal import LegalService
from app.services.readiness import ReadinessService
from app.services.roles import RoleService
from app.services.tenants import TenantService
from app.services.users import UserService

bearer_scheme = HTTPBearer(auto_error=False)


def get_readiness_service(request: Request) -> ReadinessService:
    return request.app.state.readiness_service


async def get_database_session(request: Request) -> AsyncIterator[AsyncSession]:
    database: Database = request.app.state.database
    async with database.session_factory() as session:
        yield session


async def get_tenant_context_database_session(
    request: Request,
) -> AsyncIterator[AsyncSession]:
    database: Database = request.app.state.database
    async with database.session_factory() as session:
        yield session


def get_authentication_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> AuthenticationService:
    return AuthenticationService(
        repository=AuthenticationRepository(session),
        email_protector=EmailIdentityProtector(request.app.state.openbao),
        password_manager=request.app.state.password_manager,
        access_tokens=request.app.state.access_tokens,
        refresh_token_lifetime=request.app.state.refresh_token_lifetime,
    )


def get_tenant_context_authentication_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_tenant_context_database_session)],
) -> AuthenticationService:
    return AuthenticationService(
        repository=AuthenticationRepository(session),
        email_protector=EmailIdentityProtector(request.app.state.openbao),
        password_manager=request.app.state.password_manager,
        access_tokens=request.app.state.access_tokens,
        refresh_token_lifetime=request.app.state.refresh_token_lifetime,
    )


def get_role_service(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> RoleService:
    return RoleService(RoleRepository(session))


def get_contact_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> ContactService:
    return ContactService(
        repository=ContactRepository(session),
        protector=ContactDataProtector(request.app.state.openbao),
    )


def get_legal_service(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> LegalService:
    return LegalService(LegalRepository(session))


def get_tenant_service(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> TenantService:
    return TenantService(TenantRepository(session))


def get_user_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> UserService:
    return UserService(
        repository=UserRepository(session),
        email_protector=EmailIdentityProtector(request.app.state.openbao),
    )


async def get_tenant_context(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    service: Annotated[
        AuthenticationService,
        Depends(get_tenant_context_authentication_service),
    ],
) -> TenantContext:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        token = ""
    else:
        token = credentials.credentials
    context = await service.authenticate_access_token(token)
    request.state.tenant_context = context
    return context


async def require_legal_acceptances(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
) -> TenantContext:
    if context.pending_legal_version_ids:
        raise ApplicationError(
            code="legal_acceptance_required",
            message="One or more legal documents require acceptance.",
            status_code=428,
            details={
                "pending_version_ids": [
                    str(version_id) for version_id in context.pending_legal_version_ids
                ]
            },
        )
    return context


def require_permission(permission_code: str):
    async def permission_dependency(
        context: Annotated[TenantContext, Depends(require_legal_acceptances)],
    ) -> TenantContext:
        if permission_code not in context.permissions:
            raise ApplicationError(
                code="permission_denied",
                message="Permission denied.",
                status_code=403,
            )
        return context

    return permission_dependency
