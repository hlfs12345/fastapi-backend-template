from functools import lru_cache

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EDISK_",
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "eDisk API"
    environment: str = "development"
    log_level: str = "INFO"

    database_url: SecretStr
    redis_url: SecretStr
    openbao_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8200")
    openbao_token: SecretStr | None = None
    dependency_timeout_seconds: float = Field(default=2.0, gt=0, le=30)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
