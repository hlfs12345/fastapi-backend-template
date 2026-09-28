import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_unexpected_error_is_not_exposed(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    app: FastAPI = create_app(settings)

    @app.get("/test-error")
    async def test_error() -> None:
        raise RuntimeError("sensitive internal detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/test-error", headers={"X-Request-ID": "known-request-id"})

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_server_error",
            "message": "An unexpected error occurred.",
        },
        "request_id": "known-request-id",
    }
    assert "sensitive internal detail" not in response.text
    assert "sensitive internal detail" not in capsys.readouterr().err


def test_invalid_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "invalid request id"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "invalid request id"
