"""Configuration settings for the Gardebot application."""

from typing import TypedDict

from dotenv import load_dotenv

load_dotenv()

# API configuration
API_CONFIG = {
    "base_url": "http://localhost:3000",
    "timeout": 10,  # Request timeout in seconds
    "retry_attempts": 3,
    "backoff_factor": 0.5,
    "session": "default",
}


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
