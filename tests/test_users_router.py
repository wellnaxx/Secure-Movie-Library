"""Registration failures and password-change revocation across HTTP boundaries."""

import unittest
from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from config.database import DBConfig
from config.jwt import JWTConfig
from data.models import UserPublic
from exception_handlers import register_exception_handlers
from routers.users import users_router
from utils.errors import DatabaseError

if TYPE_CHECKING:
    from repositories.user_repository import UserRow


class DriverError(Exception):
    """MariaDB-style errors for end-to-end registration failure tests."""

    def __init__(self, errno: int, sqlstate: str) -> None:
        """Attach driver error metadata while retaining a private diagnostic message."""
        super().__init__("private driver details and duplicate value")
        self.errno = errno
        self.sqlstate = sqlstate


class RegistrationRouterTests(unittest.TestCase):
    """Verify HTTP registration through real error translation with mocked drivers."""

    def setUp(self) -> None:
        """Mount registration with mocked lookup/insert connections and deterministic hashing."""
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(users_router)
        self.client = TestClient(app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.lookup = Mock()
        self.insert = Mock()
        self.lookup.cursor.return_value.description = [("id",)]
        self.lookup.cursor.return_value.fetchone.return_value = None
        self.body = {"username": "testuser", "password": "SecurePass1!"}
        config = patch("data.database._get_db_config", return_value=DBConfig("localhost", "movies", "user", ""))
        config.start()
        self.addCleanup(config.stop)
        connections = patch("data.database._get_connection", side_effect=[self.lookup, self.insert])
        self.connections = connections.start()
        self.addCleanup(connections.stop)
        hashing = patch("services.user_service.hash_password", return_value="stored-hash")
        self.hashing = hashing.start()
        self.addCleanup(hashing.stop)

    def test_duplicate_after_successful_precheck_returns_409(self) -> None:
        self.insert.cursor.return_value.execute.side_effect = DriverError(1062, "23000")
        with self.assertNoLogs("data.database", level="ERROR"):
            response = self.client.post("/users/register", json=self.body)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": "Username is already taken."})
        self.assertNotIn("private driver details", response.text)
        self.assertEqual(self.connections.call_count, 2)
        self.insert.commit.assert_not_called()
        self.insert.rollback.assert_called_once_with()
        self.lookup.close.assert_called_once_with()
        self.insert.cursor.return_value.close.assert_called_once_with()
        self.insert.close.assert_called_once_with()

    def test_other_database_failures_return_500_without_private_details(self) -> None:
        for code, state in ((1452, "23000"), (1048, "23000"), (2002, "HY000")):
            self.connections.side_effect = [self.lookup, self.insert]
            self.insert.cursor.return_value.execute.side_effect = DriverError(code, state)
            with (
                self.subTest(code=code),
                self.assertLogs("data.database", level="ERROR"),
                self.assertLogs("exception_handlers", level="ERROR"),
            ):
                response = self.client.post("/users/register", json=self.body)
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.json(), {"detail": "Database operation failed."})
            self.assertNotIn("private driver details", response.text)
            self.assertNotIn("Username is already taken", response.text)

    def test_preexisting_username_returns_409_without_insert_or_hashing(self) -> None:
        existing = {"username": "testuser"}
        with patch("services.user_service.get_user_by_username", return_value=existing):
            response = self.client.post("/users/register", json=self.body)
        self.assertEqual(response.status_code, 409)
        self.hashing.assert_not_called()
        self.connections.assert_not_called()

    def test_successful_registration_remains_201_and_public(self) -> None:
        user = UserPublic(id=1, username="testuser", role="USER", created_at=datetime(2026, 1, 1))
        with patch("routers.users.register_user", return_value=user):
            response = self.client.post("/users/register", json=self.body)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["username"], "testuser")
        self.assertNotIn("password_hash", response.json())


class PasswordChangeRouterTests(unittest.TestCase):
    """Check real JWT revocation with deterministic hashing and mocked persistence."""

    def setUp(self) -> None:
        """Mount real auth dependencies with a mutable, strictly validated account row."""
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(users_router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.row: UserRow = {
            "id": 1,
            "username": "testuser",
            "password_hash": self.hash_password("OldPass123!"),
            "role": "USER",
            "token_version": 4,
            "created_at": datetime(2026, 1, 1),
        }
        patches = (
            patch("auth.jwt_handler.get_jwt_config", return_value=JWTConfig(secret_key="s" * 32)),
            patch("repositories.user_repository.read_query_one", return_value=self.row),
            patch("services.user_service.hash_password", side_effect=self.hash_password),
            patch("services.user_service.verify_password", side_effect=self.verify_password),
        )
        for context in patches:
            context.start()
            self.addCleanup(context.stop)

    @staticmethod
    def hash_password(password: str) -> str:
        """Provide a deterministic test-only hash; production uses bcrypt."""
        return f"hashed:{password}"

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Compare credentials against the deterministic fixture hash."""
        return password_hash == PasswordChangeRouterTests.hash_password(password)

    def persist_password(self, _sql: str, params: tuple[str, int]) -> int:
        """Model a successful repository write for subsequent JWT/account reads."""
        password_hash, user_id = params
        self.assertEqual(user_id, self.row["id"])
        self.row["password_hash"] = password_hash
        self.row["token_version"] += 1
        return 1

    def test_password_change_revokes_existing_pairs_and_allows_login_with_new_password(self) -> None:
        tokens = self.client.post(
            "/users/login", data={"username": "testuser", "password": "OldPass123!"}
        ).json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        with patch("repositories.user_repository.write_query", side_effect=self.persist_password) as write:
            response = self.client.post(
                "/users/change-password",
                headers=headers,
                json={"old_password": "OldPass123!", "new_password": "NewPass123!"},
            )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        write.assert_called_once()
        self.assertEqual(self.row["token_version"], 5)
        self.assertEqual(self.row["password_hash"], self.hash_password("NewPass123!"))
        access = self.client.get("/users/me", headers=headers)
        refresh = self.client.post("/users/refresh", json={"refresh_token": tokens["refresh_token"]})
        for result in (access, refresh):
            self.assertEqual(result.status_code, 401)
            self.assertEqual(result.headers["www-authenticate"], "Bearer")
        self.assertEqual(
            self.client.post(
                "/users/login", data={"username": "testuser", "password": "OldPass123!"}
            ).status_code,
            401,
        )
        login = self.client.post("/users/login", data={"username": "testuser", "password": "NewPass123!"})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(
            self.client.get(
                "/users/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/users/refresh", json={"refresh_token": login.json()["refresh_token"]}
            ).status_code,
            200,
        )

    def test_failed_password_write_keeps_existing_credentials_and_tokens_usable(self) -> None:
        tokens = self.client.post(
            "/users/login", data={"username": "testuser", "password": "OldPass123!"}
        ).json()
        before = self.row.copy()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        with (
            patch(
                "repositories.user_repository.write_query", side_effect=DatabaseError("private details")
            ) as write,
            self.assertLogs("exception_handlers", level="ERROR"),
        ):
            response = self.client.post(
                "/users/change-password",
                headers=headers,
                json={"old_password": "OldPass123!", "new_password": "NewPass123!"},
            )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "Database operation failed."})
        write.assert_called_once()
        self.assertEqual(self.row, before)
        self.assertEqual(self.client.get("/users/me", headers=headers).status_code, 200)
        self.assertEqual(
            self.client.post("/users/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/users/login", data={"username": "testuser", "password": "OldPass123!"}
            ).status_code,
            200,
        )
