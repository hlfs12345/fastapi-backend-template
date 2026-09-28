import logging
import re
from time import perf_counter
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.request_context import reset_request_id, set_request_id

logger = logging.getLogger(__name__)
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied_request_id = request.headers.get(self.header_name)
        request_id = (
            supplied_request_id
            if supplied_request_id and _REQUEST_ID_PATTERN.fullmatch(supplied_request_id)
            else str(uuid4())
        )
        request.state.request_id = request_id
        token = set_request_id(request_id)
        started_at = perf_counter()
        try:
            response = await call_next(request)
            response.headers[self.header_name] = request_id
            route = request.scope.get("route")
            logger.info(
                "http_request_completed",
                extra={
                    "event": "http_request_completed",
                    "http_method": request.method,
                    "http_route": getattr(route, "path", "unmatched"),
                    "http_status_code": response.status_code,
                    "duration_ms": round((perf_counter() - started_at) * 1000, 2),
                },
            )
            return response
        finally:
            reset_request_id(token)
