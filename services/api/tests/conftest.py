from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://test:test@127.0.0.1:5432/test",
        redis_url="redis://127.0.0.1:6379/0",
        openbao_url="http://127.0.0.1:8200",
        dependency_timeout_seconds=0.1,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
