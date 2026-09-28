from unittest.mock import AsyncMock

import pytest

from app.services.readiness import ReadinessService


@pytest.mark.asyncio
async def test_readiness_reports_each_dependency() -> None:
    database_check = AsyncMock()
    redis_check = AsyncMock(side_effect=ConnectionError)
    openbao_check = AsyncMock()
    service = ReadinessService(
        database_check=database_check,
        redis_check=redis_check,
        openbao_check=openbao_check,
        timeout_seconds=0.1,
    )

    result = await service.check()

    assert result.status == "not_ready"
    assert result.dependencies["postgres"].status == "up"
    assert result.dependencies["redis"].status == "down"
    assert result.dependencies["openbao"].status == "up"
