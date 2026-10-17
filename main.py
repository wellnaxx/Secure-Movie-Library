"""FastAPI application with startup logging and HTTP request instrumentation."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from middleware.request_logging import RequestLoggingMiddleware
from routers.movies import movies_router
from routers.users import users_router
from utils.logging_config import configure_logging

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """Configure logging once per startup and record application lifecycle events."""
    configure_logging()
    logger.info("Secure Movie Library starting")
    try:
        yield
    finally:
        logger.info("Secure Movie Library stopping")


app = FastAPI(
    title="Secure Movie Library",
    description=(
        "A secure FastAPI application for managing movies "
        "and enriching them with OMDb ratings in the background."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)
app.include_router(users_router)
app.include_router(movies_router)
