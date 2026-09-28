import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.db.database import Database
from app.integrations.openbao import OpenBaoClient
from app.integrations.redis import RedisClient
from app.services.readiness import ReadinessService


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        active_settings = settings or get_settings()
        configure_logging(active_settings.log_level)

        database = Database(active_settings.database_url.get_secret_value())
        redis = RedisClient(active_settings.redis_url.get_secret_value())
        openbao = OpenBaoClient(
            base_url=str(active_settings.openbao_url),
            token=(
                active_settings.openbao_token.get_secret_value()
                if active_settings.openbao_token
                else None
            ),
            timeout_seconds=active_settings.dependency_timeout_seconds,
        )
        application.state.readiness_service = ReadinessService(
            database_check=database.check_connection,
            redis_check=redis.check_connection,
            openbao_check=openbao.check_health,
            timeout_seconds=active_settings.dependency_timeout_seconds,
        )
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
