"""Configuration management for Gardebot using Pydantic models."""

from __future__ import annotations

from pydantic import AnyHttpUrl, BaseModel, Field


class ServerSettings(BaseModel):
    """Settings related to the server configuration."""

    host: str = Field(default="0.0.0.0", env="SERVER_HOST")  # type: ignore
    port: int = Field(default=5000, env="SERVER_PORT")  # type: ignore
    debug: bool = Field(default=False, env="SERVER_DEBUG")  # type: ignore
    postpone_sync_time: int = Field(default=5, env="POSTPONE_SYNC_TIME")  # type: ignore


class ApiSettings(BaseModel):
    """Settings related to the WAHA API configuration."""

    base_url: AnyHttpUrl | str = Field(default="http://waha:3000", env="WAHA_BASE_URL")  # type: ignore
    session: str = Field(default="default", env="WAHA_SESSION")  # type: ignore
    timeout_seconds: int = Field(default=10, env="WAHA_TIMEOUT_SECONDS")  # type: ignore
    retry_attempts: int = Field(default=3, env="WAHA_RETRY_ATTEMPTS")  # type: ignore


class LoggingSettings(BaseModel):
    """Settings related to logging configuration."""

    level: str = Field(default="INFO", env="LOG_LEVEL")  # type: ignore
    json_logs: bool = Field(default=True, env="LOG_JSON")  # type: ignore
    color: bool = Field(default=False, env="LOG_COLOR")  # type: ignore
    timestamps: bool = Field(default=True, env="LOG_TIMESTAMPS")  # type: ignore


class AppSettings(BaseModel):
    """Aggregate application settings."""

    server: ServerSettings = ServerSettings()
    api: ApiSettings = ApiSettings()
    logging: LoggingSettings = LoggingSettings()


settings: AppSettings = AppSettings()

# Transitional compatibility if other modules still import these.
SERVER_CONFIG = {
    "host": settings.server.host,
    "port": settings.server.port,
    "debug": settings.server.debug,
    "postpone_sync_time": settings.server.postpone_sync_time,
}
API_CONFIG = {
    "base_url": settings.api.base_url,
    "session": settings.api.session,
}
