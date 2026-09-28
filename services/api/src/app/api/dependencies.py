from fastapi import Request

from app.services.readiness import ReadinessService


def get_readiness_service(request: Request) -> ReadinessService:
    return request.app.state.readiness_service
