"""HTTP request logging, streaming, privacy, and application startup tests."""

from __future__ import annotations

import unittest
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient
from starlette.background import BackgroundTask

from main import app as application
from middleware.request_logging import RequestLoggingMiddleware

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class RequestLoggingTests(unittest.TestCase):
    """Exercise ASGI status/timing records, privacy, streaming, and failure paths."""

    def setUp(self) -> None:
        """Build routes for success, validation, streaming, denial, and background failures."""
        self.app = FastAPI()
        self.app.add_middleware(RequestLoggingMiddleware)
        self.app.add_api_route("/ok", self.success, methods=["GET", "POST"])
        self.app.add_api_route("/items/{item_id}", self.item)
        self.app.add_api_route("/denied", self.denied)
        self.app.add_api_route("/error", self.error)
        self.app.add_api_route("/stream", self.stream)
        self.app.add_api_route("/background-error", self.background_error)
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    @staticmethod
    def success() -> dict[str, bool]:
        """Return a fixed body for successful GET/POST request-log assertions."""
        return {"ok": True}

    @staticmethod
    def item(item_id: int) -> dict[str, int]:
        """Echo a validated path parameter for framework-error logging assertions."""
        return {"id": item_id}

    @staticmethod
    def denied() -> None:
        """Raise a handled authentication error whose delivered status should be logged."""
        raise HTTPException(status_code=401, detail="Authentication required")

    @staticmethod
    def error() -> None:
        """Raise an unexpected exception for request and background failure scenarios."""
        raise RuntimeError("unexpected failure")

    @staticmethod
    async def stream() -> StreamingResponse:
        """Return multiple body chunks to verify transparent streaming and one completion record."""
        async def chunks() -> AsyncIterator[bytes]:
            """Yield two body chunks without buffering them into a single response."""
            yield b"first"
            yield b"second"

        return StreamingResponse(chunks())

    @staticmethod
    def background_error() -> JSONResponse:
        """Deliver HTTP 201 before a background task raises an unexpected failure."""
        return JSONResponse(
            {"created": True}, status_code=201, background=BackgroundTask(RequestLoggingTests.error)
        )

    def test_success_logs_method_path_status_and_duration(self) -> None:
        with (
            patch("middleware.request_logging.perf_counter", side_effect=[100.0, 100.125]),
            self.assertLogs("middleware.request_logging", level="INFO") as captured,
        ):
            response = self.client.get("/ok")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(captured.records), 1)
        record = captured.records[0]
        self.assertEqual(record.__dict__["method"], "GET")
        self.assertEqual(record.__dict__["path"], "/ok")
        self.assertEqual(record.__dict__["status_code"], 200)
        self.assertEqual(record.__dict__["duration_ms"], 125.0)
        self.assertIn("125.0ms", record.getMessage())

    def test_query_strings_headers_and_bodies_are_not_recorded(self) -> None:
        with self.assertLogs("middleware.request_logging", level="INFO") as captured:
            response = self.client.post(
                "/ok?token=query-secret",
                headers={"Authorization": "Bearer header-secret"},
                json={"password": "body-secret"},
            )
        self.assertEqual(response.status_code, 200)
        logs = " ".join(captured.output)
        for secret in ("query-secret", "header-secret", "body-secret"):
            self.assertNotIn(secret, logs)
        self.assertEqual(captured.records[0].__dict__["path"], "/ok")

    def test_handled_errors_are_logged_with_their_response_status(self) -> None:
        for path, status in (("/missing", 404), ("/denied", 401), ("/items/not-an-integer", 422)):
            with (
                self.subTest(path=path),
                self.assertLogs("middleware.request_logging", level="INFO") as captured,
            ):
                response = self.client.get(path)
            self.assertEqual(response.status_code, status)
            self.assertEqual(len(captured.records), 1)
            self.assertEqual(captured.records[0].__dict__["status_code"], status)
            self.assertIsNone(captured.records[0].exc_info)

    def test_unhandled_errors_are_logged_with_traceback_and_reraised(self) -> None:
        with (
            TestClient(self.app) as client,
            self.assertLogs("middleware.request_logging", level="ERROR") as captured,
            self.assertRaisesRegex(RuntimeError, "unexpected failure"),
        ):
            client.get("/error")
        self.assertEqual(captured.records[0].__dict__["status_code"], 500)
        self.assertIsNotNone(captured.records[0].exc_info)
        with self.assertLogs("middleware.request_logging", level="ERROR"):
            self.assertEqual(self.client.get("/error").status_code, 500)

    def test_streaming_response_is_unchanged_and_logged_once(self) -> None:
        with self.assertLogs("middleware.request_logging", level="INFO") as captured:
            response = self.client.get("/stream")
        self.assertEqual(response.content, b"firstsecond")
        self.assertEqual(len(captured.records), 1)
        self.assertEqual(captured.records[0].__dict__["status_code"], 200)

    def test_background_failure_retains_the_delivered_status(self) -> None:
        with self.assertLogs("middleware.request_logging", level="INFO") as captured:
            response = self.client.get("/background-error")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(captured.records), 2)
        self.assertEqual(captured.records[0].__dict__["status_code"], 201)
        self.assertEqual(captured.records[1].__dict__["status_code"], 201)
        self.assertIn("after response completion", captured.records[1].getMessage())
        self.assertIsNotNone(captured.records[1].exc_info)

    def test_path_control_characters_are_escaped_in_messages(self) -> None:
        with self.assertLogs("middleware.request_logging", level="INFO") as captured:
            self.client.get("/missing%0Aforged")
        message = captured.records[0].getMessage()
        self.assertNotIn("\n", message)
        self.assertIn("\\n", message)


class NonHTTPRequestLoggingTests(unittest.IsolatedAsyncioTestCase):
    """Verify that non-HTTP traffic passes through without request records."""

    async def test_non_http_scopes_pass_through_without_logging(self) -> None:
        for kind in ("lifespan", "websocket"):
            app = AsyncMock()
            middleware = RequestLoggingMiddleware(app)
            receive, send = AsyncMock(), AsyncMock()
            with self.subTest(kind=kind), patch("middleware.request_logging.logger") as logger:
                await middleware({"type": kind}, receive, send)
            app.assert_awaited_once_with({"type": kind}, receive, send)
            logger.info.assert_not_called()
            logger.exception.assert_not_called()


class ApplicationLoggingTests(unittest.TestCase):
    """Verify lifespan setup and request logging in the assembled application."""

    def test_logging_is_configured_once_per_startup_and_main_app_logs_requests(self) -> None:
        with (
            patch("main.configure_logging") as configure,
            self.assertLogs("main", level="INFO") as lifecycle,
            self.assertLogs("middleware.request_logging", level="INFO") as requests,
            TestClient(application) as client,
        ):
            self.assertEqual(client.get("/openapi.json").status_code, 200)
            self.assertEqual(client.get("/docs").status_code, 200)
        configure.assert_called_once_with()
        self.assertEqual(len(requests.records), 2)
        self.assertIn("starting", lifecycle.records[0].getMessage())
        self.assertIn("stopping", lifecycle.records[1].getMessage())

    def test_invalid_logging_setup_fails_startup(self) -> None:
        with (
            patch("main.configure_logging", side_effect=ValueError("Invalid LOG_LEVEL")),
            self.assertRaisesRegex(ValueError, "LOG_LEVEL"),
            TestClient(application),
        ):
            self.fail("Startup should not succeed with invalid logging settings")
