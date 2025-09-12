"""Configuration settings for the Gardebot application."""

from typing import TypedDict

# API configuration


class ApiConfigType(TypedDict):
    """TypedDict for API configuration."""

    base_url: str
    timeout: int
    retry_attempts: int
    backoff_factor: float
    session: str


API_CONFIG: ApiConfigType = {
    "base_url": "http://waha:3000",
    "timeout": 10,  # Request timeout in seconds
    "retry_attempts": 3,
    "backoff_factor": 0.5,
    "session": "default",
}

GROUP_ID_GARDE_ET_PIQUET = "120363402596282813@g.us"


class ServerConfigType(TypedDict):
    """TypedDict for server configuration."""

    host: str
    port: int
    debug: bool


SERVER_CONFIG: ServerConfigType = {
    "host": "0.0.0.0",
    "port": 5000,
    "debug": False,
    # other config values...
}
