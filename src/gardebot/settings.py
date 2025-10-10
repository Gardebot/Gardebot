"""Configuration management for Gardebot using Pydantic models."""

from __future__ import annotations

import os

from pydantic import AnyHttpUrl, BaseModel, Field


class ServerSettings(BaseModel):
    """Settings related to the server configuration."""

    host: str = Field(default="0.0.0.0", env="SERVER_HOST")
    port: int = Field(default=5000, env="SERVER_PORT")
    debug: bool = Field(default=False, env="SERVER_DEBUG")
    postpone_sync_time: int = Field(default=5, env="POSTPONE_SYNC_TIME")


class ApiSettings(BaseModel):
    """Settings related to the WAHA API configuration."""

    base_url: AnyHttpUrl | str = Field(default="http://waha:3000", env="WAHA_BASE_URL")
    session: str = Field(default="default", env="WAHA_SESSION")
    timeout_seconds: int = Field(default=10, env="WAHA_TIMEOUT_SECONDS")
    retry_attempts: int = Field(default=3, env="WAHA_RETRY_ATTEMPTS")


class LoggingSettings(BaseModel):
    """Settings related to logging configuration."""

    level: str = Field(default="INFO", env="LOG_LEVEL")
    json_logs: bool = Field(default=True, env="LOG_JSON")
    color: bool = Field(default=False, env="LOG_COLOR")
    timestamps: bool = Field(default=True, env="LOG_TIMESTAMPS")


class AppSettings(BaseModel):
    """Aggregate application settings."""

    server: ServerSettings = ServerSettings()
    api: ApiSettings = ApiSettings()
    logging: LoggingSettings = LoggingSettings()


settings = AppSettings()

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
