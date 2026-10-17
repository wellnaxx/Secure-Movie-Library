"""Stdout and rotating-file application logging, adapted from FleetFlow."""

import logging
import sys
from logging.handlers import RotatingFileHandler

from config.logging import LoggingConfig, get_logging_config


def configure_logging(config: LoggingConfig | None = None) -> None:
    """Configure root logging at startup without accumulating duplicate handlers.

    A file destination rotates at 10 MiB and retains five backups. Invalid file
    destinations propagate their filesystem errors so startup does not silently
    discard logs. Callers configure logging once per application startup.
    """
    config = config if config is not None else get_logging_config()
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if config.log_file is not None:
        config.log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                config.log_file,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
        )
    for handler in handlers:
        handler.setFormatter(formatter)
    logging.basicConfig(level=config.level, handlers=handlers, force=True)

    # Request middleware replaces Uvicorn access records. HTTP client logs can
    # contain full outbound URLs, including the OMDb API key in query parameters.
    for name in ("uvicorn.access", "httpx", "httpcore", "multipart", "python_multipart"):
        logging.getLogger(name).setLevel(logging.WARNING)
