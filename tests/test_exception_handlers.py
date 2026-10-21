"""Centralized HTTP mappings, sanitization, and operation-specific user failures."""

import unittest
from datetime import datetime
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from data.models import UserInternal
from dependencies.auth import get_current_admin, get_current_user
from exception_handlers import register_exception_handlers
from main import app as application
from routers.users import users_router
from utils.errors import (
    AuthenticationError,
    AuthorizationError,
    DatabaseError,
    DuplicateKeyError,
    EmptyMovieUpdateError,
    IncorrectOldPasswordError,
    InvalidAccessTokenError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    MovieCreationError,
    MovieDeleteError,
    MovieNotFoundError,
    MovieServiceError,
    RepositoryError,
    UserCreationError,
    UsernameAlreadyExistsError,
    UserNotFoundError,
    UserServiceError,
)


class ExceptionHandlerTests(unittest.TestCase):
    """Exercise registered handlers through an isolated FastAPI application."""

    def setUp(self) -> None:
        """Build failure and validation routes with shared handlers and a non-raising client."""
        self.error: Exception = RuntimeError("private details")
        self.app = FastAPI()
        register_exception_handlers(self.app)
        self.app.add_api_route("/failure", self.failure)
        self.app.add_api_route("/validated/{item_id}", self.validated)
        self.app.add_api_route("/http-error", self.http_error)
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def failure(self) -> None:
        """Raise the selected exception from an HTTP endpoint so registered handlers process it."""
        raise self.error

    @staticmethod
    def validated(item_id: int) -> dict[str, int]:
        """Return a typed path value to exercise the framework validation handler."""
        return {"id": item_id}

    @staticmethod
    def http_error() -> None:
        """Raise a framework HTTPException with an existing bearer challenge."""
        raise HTTPException(
            status_code=401, detail="Existing HTTP error", headers={"WWW-Authenticate": "Bearer"}
        )

    def test_expected_application_errors_preserve_status_and_public_message(self) -> None:
        cases: list[tuple[Exception, int]] = [
            (UsernameAlreadyExistsError("username conflict"), 409),
            (MovieNotFoundError("movie missing"), 404),
            (UserNotFoundError("user missing"), 404),
            (EmptyMovieUpdateError("empty update"), 400),
            (IncorrectOldPasswordError("incorrect password"), 400),
            (AuthorizationError("admin required"), 403),
            (MovieCreationError("movie creation failed"), 500),
            (MovieDeleteError("movie deletion failed"), 500),
            (UserCreationError("user creation failed"), 500),
        ]
        for error, expected in cases:
            self.error = error
            with self.subTest(error=type(error).__name__), patch("exception_handlers.logger") as logger:
                response = self.client.get("/failure")
            self.assertEqual(response.status_code, expected)
            self.assertEqual(response.json(), {"detail": str(error)})
            self.assertNotIn("www-authenticate", response.headers)
            if expected == 500:
                self.assertIs(logger.error.call_args.kwargs["exc_info"][1], error)
            else:
                logger.error.assert_not_called()

    def test_all_authentication_error_types_have_a_bearer_challenge(self) -> None:
        for error in (
            AuthenticationError,
            InvalidAccessTokenError,
            InvalidCredentialsError,
            InvalidRefreshTokenError,
        ):
            self.error = error("Authentication failed")
            with self.subTest(error=error.__name__):
                response = self.client.get("/failure")
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.headers["www-authenticate"], "Bearer")
            self.assertEqual(response.json(), {"detail": "Authentication failed"})

    def test_duplicate_key_is_specific_and_sanitized(self) -> None:
        self.error = DuplicateKeyError("private constraint and duplicate value")
        with patch("exception_handlers.logger") as logger:
            response = self.client.get("/failure")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": "A record with the same unique key already exists."})
        logger.error.assert_not_called()

    def test_repository_errors_have_stable_json_without_driver_details(self) -> None:
        for error in (RepositoryError, DatabaseError):
            self.error = error("private SQL, host, and credentials")
            with (
                self.subTest(error=error.__name__),
                self.assertLogs("exception_handlers", level="ERROR") as logs,
            ):
                response = self.client.get("/failure")
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.json(), {"detail": "Database operation failed."})
            info = logs.records[0].exc_info
            if info is None:
                self.fail("Repository failures must include a traceback")
            self.assertIs(info[1], self.error)

    def test_unexpected_and_unclassified_service_failures_are_sanitized(self) -> None:
        for error in (RuntimeError, ValueError, UserServiceError, MovieServiceError):
            self.error = error("private internal details")
            with self.subTest(error=error.__name__), self.assertLogs("exception_handlers", level="ERROR"):
                response = self.client.get("/failure")
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.json(), {"detail": "Internal server error."})

    def test_failure_logs_record_tracebacks_and_omit_query_strings(self) -> None:
        with self.assertLogs("exception_handlers", level="ERROR") as logs:
            response = self.client.get(
                "/failure?token=query-secret", headers={"Authorization": "Bearer header-secret"}
            )
        self.assertEqual(response.status_code, 500)
        message = logs.records[0].getMessage()
        self.assertIn("GET '/failure'", message)
        self.assertNotIn("query-secret", message)
        self.assertNotIn("header-secret", message)
        self.assertIsNotNone(logs.records[0].exc_info)

    def test_framework_validation_and_http_exception_handlers_remain_intact(self) -> None:
        self.assertEqual(self.client.get("/validated/not-an-integer").status_code, 422)
        self.assertEqual(self.client.get("/not-a-route").status_code, 404)
        response = self.client.get("/http-error")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["www-authenticate"], "Bearer")
        self.assertEqual(response.json(), {"detail": "Existing HTTP error"})

    def test_registration_is_idempotent(self) -> None:
        before = self.app.exception_handlers.copy()
        register_exception_handlers(self.app)
        self.assertEqual(self.app.exception_handlers, before)


class UserFailureContextTests(unittest.TestCase):
    """Keep user-operation error meanings consistent through real service calls."""

    def setUp(self) -> None:
        """Mount user routes with shared handlers and a fixed authenticated admin."""
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(users_router)
        self.app = app
        self.app.dependency_overrides[get_current_user] = self.admin
        self.app.dependency_overrides[get_current_admin] = self.admin
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    @staticmethod
    def admin() -> UserInternal:
        """Supply a fixed internal admin account without consulting authentication or persistence."""
        return UserInternal(
            id=1, username="admin", password_hash="hash", role="ADMIN", created_at=datetime(2026, 1, 1)
        )

    def test_registration_reload_failure_is_500(self) -> None:
        with (
            patch("services.user_service.get_user_by_username", return_value=None),
            patch("services.user_service.hash_password", return_value="hash"),
            patch("services.user_service.create_user", return_value=1),
            patch("services.user_service.get_user_by_id", return_value=None),
            self.assertLogs("exception_handlers", level="ERROR"),
        ):
            response = self.client.post(
                "/users/register", json={"username": "newuser", "password": "SecurePass1!"}
            )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "User was created, but could not be loaded afterwards."})

    def test_refresh_for_deleted_user_is_401(self) -> None:
        with (
            patch("services.user_service.decode_token", return_value={"sub": "1", "token_version": 0}),
            patch("services.user_service.get_user_by_id", return_value=None),
        ):
            response = self.client.post("/users/refresh", json={"refresh_token": "token"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["www-authenticate"], "Bearer")
        self.assertEqual(response.json(), {"detail": "User not found."})

    def test_role_update_for_missing_user_is_404(self) -> None:
        with patch("services.user_service.get_user_by_id", return_value=None):
            response = self.client.patch("/users/99/role", json={"role": "USER"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "User not found."})

    def test_login_failure_remains_401(self) -> None:
        with patch(
            "routers.users.authenticate_user",
            side_effect=InvalidCredentialsError("Invalid username or password."),
        ):
            response = self.client.post("/users/login", data={"username": "user", "password": "wrong"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["www-authenticate"], "Bearer")

    def test_refresh_failure_remains_401(self) -> None:
        with patch(
            "routers.users.refresh_token_pair", side_effect=InvalidRefreshTokenError("Invalid refresh token.")
        ):
            response = self.client.post("/users/refresh", json={"refresh_token": "token"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["www-authenticate"], "Bearer")

    def test_incorrect_old_password_remains_400(self) -> None:
        with patch(
            "routers.users.change_password", side_effect=IncorrectOldPasswordError("Old password is incorrect.")
        ):
            response = self.client.post(
                "/users/change-password",
                json={
                    "old_password": "OldPass123!",
                    "new_password": "NewPass123!",
                },
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "Old password is incorrect."})

    def test_logout_persistence_failure_uses_repository_handler(self) -> None:
        with (
            patch("routers.users.bump_token_version", side_effect=DatabaseError("private driver details")),
            self.assertLogs("exception_handlers", level="ERROR"),
        ):
            response = self.client.post("/users/logout")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "Database operation failed."})

    def test_missing_bearer_token_still_uses_framework_challenge(self) -> None:
        self.app.dependency_overrides.clear()
        response = self.client.get("/users/me")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["www-authenticate"], "Bearer")


class MainApplicationHandlerTests(unittest.TestCase):
    """Verify main-app handler registration and request-logging interaction."""

    def test_main_app_handles_repository_failures_and_logs_completed_status(self) -> None:
        with (
            patch("main.configure_logging"),
            patch("routers.users.authenticate_user", side_effect=DatabaseError("private connection details")),
            self.assertLogs("exception_handlers", level="ERROR"),
            self.assertLogs("middleware.request_logging", level="INFO") as requests,
            TestClient(application) as client,
        ):
            response = client.post("/users/login", data={"username": "user", "password": "password"})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "Database operation failed."})
        self.assertEqual(len(requests.records), 1)
        self.assertEqual(requests.records[0].__dict__["status_code"], 500)
        self.assertIsNone(requests.records[0].exc_info)

    def test_main_app_fallback_returns_sanitized_json_and_keeps_failure_logging(self) -> None:
        with (
            patch("main.configure_logging"),
            patch("routers.users.authenticate_user", side_effect=RuntimeError("private unexpected details")),
            self.assertLogs("exception_handlers", level="ERROR"),
            self.assertLogs("middleware.request_logging", level="ERROR") as requests,
            TestClient(application, raise_server_exceptions=False) as client,
        ):
            response = client.post("/users/login", data={"username": "user", "password": "password"})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "Internal server error."})
        self.assertEqual(len(requests.records), 1)
        self.assertIsNotNone(requests.records[0].exc_info)
