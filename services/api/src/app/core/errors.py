import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.request_context import get_request_id

logger = logging.getLogger(__name__)


class ApplicationError(Exception):
    def __init__(self, *, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _error_content(
    *,
    code: str,
    message: str,
    request_id: str | None = None,
    details: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"error": error, "request_id": request_id or get_request_id()}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def application_error_handler(request: Request, error: ApplicationError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content=_error_content(
                code=error.code,
                message=error.message,
                request_id=getattr(request.state, "request_id", None),
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "location": [str(item) for item in validation_error["loc"]],
                "message": validation_error["msg"],
                "type": validation_error["type"],
            }
            for validation_error in error.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_error_content(
                code="request_validation_error",
                message="Request validation failed.",
                request_id=getattr(request.state, "request_id", None),
                details=details,
            ),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
        route = request.scope.get("route")
        logger.error(
            "unhandled_exception",
            extra={
                "event": "unhandled_exception",
                "http_method": request.method,
                "http_route": getattr(route, "path", "unmatched"),
                "error_type": type(error).__name__,
            },
        )
        return JSONResponse(
            status_code=500,
            content=_error_content(
                code="internal_server_error",
                message="An unexpected error occurred.",
                request_id=getattr(request.state, "request_id", None),
            ),
        )
