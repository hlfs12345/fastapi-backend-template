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
    openbao_role_id: SecretStr | None = None
    openbao_secret_id: SecretStr | None = None
    dependency_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    auth_jwt_secret: SecretStr | None = Field(default=None, min_length=32)
    auth_access_token_minutes: int = Field(default=15, ge=1, le=60)
    auth_refresh_token_days: int = Field(default=30, ge=1, le=90)
    auth_issuer: str = "edisk-api"
    auth_audience: str = "edisk-app"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
