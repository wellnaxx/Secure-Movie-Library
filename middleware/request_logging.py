"""Request completion and failure logging without recording request payloads."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    """Observe ASGI responses without buffering bodies or changing streaming.

    Completion timing stops after the last response body is sent, before any
    background tasks finish. Unhandled failures are logged and re-raised; failures
    after response completion retain the status already delivered to the client.
    Lifespan and WebSocket traffic pass through without HTTP request records.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Wrap the next ASGI application."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Log method, path, status, and elapsed time, excluding query/body/header data."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = perf_counter()
        method = scope["method"]
        path = scope["path"]
        status_code = 500
        completed = False

        async def logged_send(message: Message) -> None:
            nonlocal status_code, completed
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                completed = True
                duration_ms = (perf_counter() - start) * 1000
                logger.info(
                    "%s %r -> %d (%.1fms)",
                    method,
                    path,
                    status_code,
                    duration_ms,
                    extra={
                        "method": method,
                        "path": path,
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                    },
                )

        try:
            await self.app(scope, receive, logged_send)
        except Exception:
            duration_ms = (perf_counter() - start) * 1000
            logger.exception(
                "%s %r -> %d, unhandled error%s (%.1fms)",
                method,
                path,
                status_code,
                " after response completion" if completed else "",
                duration_ms,
                extra={"method": method, "path": path, "status_code": status_code, "duration_ms": duration_ms},
            )
            raise
