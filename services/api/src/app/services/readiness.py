import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.schemas.health import DependencyStatus, ReadinessResponse

logger = logging.getLogger(__name__)
Check = Callable[[], Awaitable[None]]


class ReadinessService:
    def __init__(
        self,
        *,
        database_check: Check,
        redis_check: Check,
        openbao_check: Check,
        timeout_seconds: float,
    ) -> None:
        self._checks = {
            "postgres": database_check,
            "redis": redis_check,
            "openbao": openbao_check,
        }
        self._timeout_seconds = timeout_seconds

    async def check(self) -> ReadinessResponse:
        names = list(self._checks)
        results = await asyncio.gather(
            *(self._run_check(name, self._checks[name]) for name in names)
        )
        dependencies = dict(zip(names, results, strict=True))
        status = "ready" if all(item.status == "up" for item in results) else "not_ready"
        return ReadinessResponse(status=status, dependencies=dependencies)

    async def _run_check(self, name: str, check: Check) -> DependencyStatus:
        try:
            await asyncio.wait_for(check(), timeout=self._timeout_seconds)
        except Exception as error:
            logger.warning(
                "dependency_check_failed",
                extra={
                    "event": "dependency_check_failed",
                    "dependency": name,
                    "error_type": type(error).__name__,
                },
            )
            return DependencyStatus(status="down")
        return DependencyStatus(status="up")
