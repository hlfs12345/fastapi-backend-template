from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_readiness_service
from app.core.config import Settings
from app.main import create_app
from app.schemas.health import DependencyStatus, ReadinessResponse


def test_liveness_does_not_check_dependencies(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
    assert response.headers["X-Request-ID"]


@pytest.mark.parametrize(
    ("readiness", "expected_status"),
    [
        (
            ReadinessResponse(
                status="ready",
                dependencies={
                    "postgres": DependencyStatus(status="up"),
                    "redis": DependencyStatus(status="up"),
                    "openbao": DependencyStatus(status="up"),
                },
            ),
            200,
        ),
        (
            ReadinessResponse(
                status="not_ready",
                dependencies={
                    "postgres": DependencyStatus(status="up"),
                    "redis": DependencyStatus(status="down"),
                    "openbao": DependencyStatus(status="up"),
                },
            ),
            503,
        ),
    ],
)
def test_readiness_maps_service_result_to_http_status(
    settings: Settings,
    readiness: ReadinessResponse,
    expected_status: int,
) -> None:
    app = create_app(settings)
    readiness_service = AsyncMock()
    readiness_service.check.return_value = readiness
    app.dependency_overrides[get_readiness_service] = lambda: readiness_service

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == expected_status
    assert response.json() == readiness.model_dump(mode="json")
    readiness_service.check.assert_awaited_once()
