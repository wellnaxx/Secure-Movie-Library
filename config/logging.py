"""Application logging settings and their lazy, replaceable cache."""

import logging
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from utils.env_vars import get_env_var

LOG_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    """Standard logging severity and optional rotating-file destination.

    None means stdout only. Relative paths use the process working directory;
    destination creation and permissions are checked when logging is configured.
    """

    level: int = logging.INFO
    log_file: Path | None = None

    def __post_init__(self) -> None:
        """Require one of the supported standard logging levels."""
        if self.level not in LOG_LEVELS.values():
            raise ValueError("LOG_LEVEL must be a supported standard logging level.")


_logging_config: LoggingConfig | None = None


def load_logging_config() -> LoggingConfig:
    """Read .env and logging settings, rejecting unsupported level names."""
    load_dotenv()
    raw_level = get_env_var("LOG_LEVEL", "INFO").strip().upper()
    try:
        level = LOG_LEVELS[raw_level]
    except KeyError as exc:
        supported = ", ".join(LOG_LEVELS)
        raise ValueError(f"Unsupported LOG_LEVEL. Supported values: {supported}.") from exc
    raw_file = get_env_var("LOG_FILE", "").strip()
    return LoggingConfig(level=level, log_file=Path(raw_file) if raw_file else None)


def get_logging_config() -> LoggingConfig:
    """Return cached settings, loading them only after the first successful read."""
    global _logging_config
    if _logging_config is None:
        _logging_config = load_logging_config()
    return _logging_config


def set_logging_config(config: LoggingConfig | None) -> None:
    """Replace cached settings, or clear them with None for a later reload."""
    global _logging_config
    _logging_config = config
