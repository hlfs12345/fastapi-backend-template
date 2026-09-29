from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import get_authentication_service, get_tenant_context
from app.core.tenant_context import TenantContext
from app.schemas.authentication import (
    AuthenticatedContextResponse,
    LoginRequest,
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
    context: Annotated[TenantContext, Depends(get_tenant_context)],
) -> AuthenticatedContextResponse:
    return AuthenticatedContextResponse(
        user_id=context.user_id,
        tenant_id=context.tenant_id,
        tenant_user_id=context.tenant_user_id,
    )


def _disable_token_response_caching(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
