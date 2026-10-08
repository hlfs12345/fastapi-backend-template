from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import (
    get_authentication_service,
    get_tenant_context,
    require_legal_acceptances,
)
from app.core.tenant_context import TenantContext
from app.schemas.authentication import (
    AuthenticatedContextResponse,
    AuthenticatedRoleResponse,
    LoginRequest,
    PasswordChangeRequest,
    RefreshRequest,
    TokenResponse,
)
from app.services.authentication import AuthenticationService

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    service: Annotated[AuthenticationService, Depends(get_authentication_service)],
) -> TokenResponse:
    tokens = await service.login(
        email=str(payload.email),
        password=payload.password.get_secret_value(),
        tenant_slug=payload.tenant_slug,
    )
    _disable_token_response_caching(response)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    response: Response,
    service: Annotated[AuthenticationService, Depends(get_authentication_service)],
) -> TokenResponse:
    tokens = await service.refresh(payload.refresh_token.get_secret_value())
    _disable_token_response_caching(response)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: RefreshRequest,
    service: Annotated[AuthenticationService, Depends(get_authentication_service)],
) -> Response:
    await service.logout(payload.refresh_token.get_secret_value())
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=AuthenticatedContextResponse)
async def me(
    response: Response,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[AuthenticationService, Depends(get_authentication_service)],
) -> AuthenticatedContextResponse:
    account = await service.get_authenticated_account(context)
    _disable_token_response_caching(response)
    return AuthenticatedContextResponse(
        user_id=account.user_id,
        email=account.email,
        tenant_id=account.tenant_id,
        tenant_name=account.tenant_name,
        tenant_slug=account.tenant_slug,
        tenant_user_id=account.tenant_user_id,
        joined_at=account.joined_at,
        roles=[AuthenticatedRoleResponse(key=role.key, name=role.name) for role in account.roles],
        permissions=list(account.permissions),
    )


@router.put("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: PasswordChangeRequest,
    context: Annotated[TenantContext, Depends(require_legal_acceptances)],
    service: Annotated[AuthenticationService, Depends(get_authentication_service)],
) -> Response:
    await service.change_password(
        context=context,
        current_password=payload.current_password.get_secret_value(),
        new_password=payload.new_password.get_secret_value(),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _disable_token_response_caching(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
