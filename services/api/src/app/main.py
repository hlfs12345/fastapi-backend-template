import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.security import AccessTokenCodec, PasswordManager
from app.db.database import Database
from app.integrations.openbao import OpenBaoClient
from app.integrations.redis import RedisClient
from app.services.readiness import ReadinessService


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        active_settings = settings or get_settings()
        configure_logging(active_settings.log_level)
        if active_settings.auth_jwt_secret is None:
            raise RuntimeError("EDISK_AUTH_JWT_SECRET is required to start the API.")

        database = Database(active_settings.database_url.get_secret_value())
        redis = RedisClient(active_settings.redis_url.get_secret_value())
        openbao = OpenBaoClient(
            base_url=str(active_settings.openbao_url),
            token=(
                active_settings.openbao_token.get_secret_value()
                if active_settings.openbao_token
                else None
            ),
            role_id=(
                active_settings.openbao_role_id.get_secret_value()
                if active_settings.openbao_role_id
                else None
            ),
            secret_id=(
                active_settings.openbao_secret_id.get_secret_value()
                if active_settings.openbao_secret_id
                else None
            ),
            timeout_seconds=active_settings.dependency_timeout_seconds,
        )
        application.state.access_tokens = AccessTokenCodec(
            secret=active_settings.auth_jwt_secret.get_secret_value(),
            issuer=active_settings.auth_issuer,
            audience=active_settings.auth_audience,
            lifetime=timedelta(minutes=active_settings.auth_access_token_minutes),
        )
        application.state.password_manager = PasswordManager()
        application.state.refresh_token_lifetime = timedelta(
            days=active_settings.auth_refresh_token_days
        )
        application.state.openbao = openbao
        application.state.readiness_service = ReadinessService(
            database_check=database.check_connection,
            redis_check=redis.check_connection,
            openbao_check=openbao.check_health,
            timeout_seconds=active_settings.dependency_timeout_seconds,
        )
        application.state.database = database
        try:
            yield
        finally:
            await asyncio.gather(database.close(), redis.close(), openbao.close())

    application = FastAPI(
        title=settings.app_name if settings else "eDisk API",
        lifespan=lifespan,
    )
    application.add_middleware(RequestContextMiddleware)
    application.include_router(api_router)
    register_exception_handlers(application)
    return application


app = create_app()
