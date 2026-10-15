"""OMDb client settings and their lazy, replaceable cache."""

import math
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from dotenv import load_dotenv

from config._validation import require_text
from utils.env_vars import get_env_var


@dataclass(frozen=True, slots=True)
class OMDbConfig:
    """OMDb credentials, endpoint, and finite HTTP timeout in seconds."""

    api_key: str = field(repr=False)
    base_url: str = "https://www.omdbapi.com/"
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        """Require an API key, an HTTP(S) endpoint, and a positive timeout."""
        require_text("OMDB_API_KEY", self.api_key)
        url = urlsplit(self.base_url)
        if url.scheme not in {"http", "https"} or not url.hostname:
            raise ValueError("OMDB_BASE_URL must be an absolute HTTP or HTTPS URL.")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("OMDB_TIMEOUT_SECONDS must be finite and greater than zero.")


_omdb_config: OMDbConfig | None = None


def load_omdb_config() -> OMDbConfig:
    """Read .env and the environment, validating a fresh configuration."""
    load_dotenv()
    try:
        timeout = float(get_env_var("OMDB_TIMEOUT_SECONDS", "10"))
    except ValueError as exc:
        raise ValueError("OMDB_TIMEOUT_SECONDS must be a number.") from exc
    return OMDbConfig(
        api_key=get_env_var("OMDB_API_KEY"),
        base_url=get_env_var("OMDB_BASE_URL", "https://www.omdbapi.com/"),
        timeout_seconds=timeout,
    )


def get_omdb_config() -> OMDbConfig:
    """Return cached settings, loading them only after the first successful read."""
    global _omdb_config
    if _omdb_config is None:
        _omdb_config = load_omdb_config()
    return _omdb_config


def set_omdb_config(config: OMDbConfig | None) -> None:
    """Replace cached settings, or clear them with None for a later reload."""
    global _omdb_config
    _omdb_config = config
