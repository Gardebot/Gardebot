"""Configuration settings for the Gardebot application."""

import os
from typing import TypedDict

from dopplersdk import DopplerSDK  # type: ignore[import-untyped]


def _load_secret(name: str, project: str = "gardebot", config: str = "dev") -> str:
    doppler = DopplerSDK()
    doppler_token = os.environ.get("DOPPLER_TOKEN")
    if not doppler_token:
        raise ValueError("DOPPLER_TOKEN environment variable is not set.")
    doppler.set_access_token(doppler_token)
    result = doppler.secrets.get(project=project, name=name, config=config)
    return str(vars(result)["value"]["raw"])


class ApiConfigType(TypedDict):
    """TypedDict for API configuration."""

    base_url: str
    timeout: int
    retry_attempts: int
    backoff_factor: float
    session: str
    api_key: str


API_CONFIG: ApiConfigType = {
    "base_url": "http://waha:3000",
    "timeout": 10,  # Request timeout in seconds
    "retry_attempts": 3,
    "backoff_factor": 0.5,
    "session": "default",
    "api_key": _load_secret("API_KEY"),
}

# GROUP_ID_GARDE_ET_PIQUET = "120363402596282813@g.us"
GROUP_ID_GARDE_ET_PIQUET = "41782611429"


class ServerConfigType(TypedDict):
    """TypedDict for server configuration."""

    host: str
    port: int
    debug: bool
    postpone_sync_time: int


SERVER_CONFIG: ServerConfigType = {
    "host": "0.0.0.0",
    "port": 5000,
    "debug": False,
    "postpone_sync_time": 60,  # Postpone sync of group participants on startup (to allow WAHA to be ready)
}

MONTHS_FR = {
    1: "janvier",
    2: "février",
    3: "mars",
    4: "avril",
    5: "mai",
    6: "juin",
    7: "juillet",
    8: "août",
    9: "septembre",
    10: "octobre",
    11: "novembre",
    12: "décembre",
}

WEEKDAYS_FR = {
    0: "lundi",
    1: "mardi",
    2: "mercredi",
    3: "jeudi",
    4: "vendredi",
    5: "samedi",
    6: "dimanche",
}

TIME_BEFORE_PUBLICATION_DAY = 21
EM_NAME = [
    "Vadim Harych",
    "David Gori",
    "Julien Haefelin",
    "Louis Bretton",
    "Jean-Seb Fourier",
    "Damien Neuenschwander",
    "Liberto Christophe",
    "Vincent Vuillemier",
    "Eilean Rieder",
    "Lionel Bidaux",
    "Christophe Zurn",
    "eSim Swisscom",
]
MAX_NB_REMINDER = 3
