from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.dependencies import get_readiness_service
from app.schemas.health import HealthResponse, ReadinessResponse
from app.services.readiness import ReadinessService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="healthy")


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def readiness(
    service: Annotated[ReadinessService, Depends(get_readiness_service)],
) -> ReadinessResponse | JSONResponse:
    result = await service.check()
    if result.status == "ready":
        return result

    return JSONResponse(status_code=503, content=result.model_dump(mode="json"))
