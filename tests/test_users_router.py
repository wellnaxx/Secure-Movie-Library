"""Registration HTTP responses across typed persistence error boundaries."""

import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from config.database import DBConfig
from data.models import UserPublic
from exception_handlers import register_exception_handlers
from routers.users import users_router


class DriverError(Exception):
    """MariaDB-style errors for end-to-end registration failure tests."""

    def __init__(self, errno: int, sqlstate: str) -> None:
        super().__init__("private driver details and duplicate value")
        self.errno = errno
        self.sqlstate = sqlstate


class RegistrationRouterTests(unittest.TestCase):
    def setUp(self) -> None:
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
