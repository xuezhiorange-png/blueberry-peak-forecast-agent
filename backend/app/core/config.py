from functools import lru_cache
from urllib.parse import quote

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Blueberry Peak Forecast Agent"
    app_env: str = "local"
    log_level: str = "INFO"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "blueberry_peak"
    postgres_user: str = "blueberry_app"
    postgres_password: SecretStr = Field(default=SecretStr("change-me-in-local-env"))

    db_pool_size: int = 5
    db_max_overflow: int = 10

    @property
    def async_database_url(self) -> str:
        user = quote(self.postgres_user)
        password = quote(self.postgres_password.get_secret_value())
        host = self.postgres_host
        port = self.postgres_port
        database = quote(self.postgres_db)
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
