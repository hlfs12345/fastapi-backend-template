from fastapi import APIRouter

from app.api.routes.authentication import router as authentication_router
from app.api.routes.health import router as health_router
from app.api.routes.roles import router as roles_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(authentication_router)
api_router.include_router(roles_router)
