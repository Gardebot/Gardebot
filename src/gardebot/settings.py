"""Configuration management for Gardebot using Pydantic models."""

from __future__ import annotations

import os

from pydantic import AnyHttpUrl, BaseModel, Field


class ServerSettings(BaseModel):
    """Settings related to the server configuration."""

    host: str = Field(default_factory=lambda: os.getenv("SERVER_HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("SERVER_PORT", "5000")))
    debug: bool = Field(default_factory=lambda: os.getenv("SERVER_DEBUG", "false").lower() == "true")
    postpone_sync_time: int = Field(default_factory=lambda: int(os.getenv("POSTPONE_SYNC_TIME", "5")))


class ApiSettings(BaseModel):
    """Settings related to the WAHA API configuration."""

    base_url: AnyHttpUrl | str = Field(default_factory=lambda: os.getenv("WAHA_BASE_URL", "http://waha:3000"))
    session: str = Field(default_factory=lambda: os.getenv("WAHA_SESSION", "default"))
    timeout_seconds: int = Field(default_factory=lambda: int(os.getenv("WAHA_TIMEOUT_SECONDS", "10")))
    retry_attempts: int = Field(default_factory=lambda: int(os.getenv("WAHA_RETRY_ATTEMPTS", "3")))


class LoggingSettings(BaseModel):
    """Settings related to logging configuration."""

    level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    json_logs: bool = Field(default_factory=lambda: os.getenv("LOG_JSON", "true").lower() == "true")
    color: bool = Field(default_factory=lambda: os.getenv("LOG_COLOR", "false").lower() == "true")
    timestamps: bool = Field(default_factory=lambda: os.getenv("LOG_TIMESTAMPS", "true").lower() == "true")


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
