"""User SQL bindings, strict database-row validation, and persistence failure contracts."""

import unittest
from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

from pydantic import ValidationError

from config.database import DBConfig
from data import database
from repositories.user_repository import (
    UserRow,
    bump_token_version,
    create_user,
    get_user_by_id,
    get_user_by_username,
    update_password,
    update_role,
)
from utils.errors import DatabaseError, DuplicateKeyError

if TYPE_CHECKING:
    from collections.abc import Callable


class UserRepositoryTests(unittest.TestCase):
    """Check validated user rows and bound persistence operations with database mocks."""

    def setUp(self) -> None:
        """Build a complete typed user row for lookup and mutation-binding assertions."""
        self.row: UserRow = {
            "id": 1,
            "username": "testuser",
            "password_hash": "stored-hash",
            "role": "USER",
            "token_version": 0,
            "created_at": datetime(2026, 1, 1),
        }

    def test_lookups_validate_rows_and_bind_search_values(self) -> None:
        cases: list[tuple[Callable[[], UserRow | None], str, tuple[object, ...]]] = [
            (lambda: get_user_by_id(1), "SELECT * FROM users WHERE id = ?", (1,)),
            (lambda: get_user_by_username("testuser"), "SELECT * FROM users WHERE username = ?", ("testuser",)),
        ]
        for lookup, sql, params in cases:
            with (
                self.subTest(sql=sql),
                patch("repositories.user_repository.read_query_one", return_value=self.row) as query,
            ):
                self.assertEqual(lookup(), self.row)
            query.assert_called_once_with(sql, params)

    def test_both_lookups_preserve_missing_user_result(self) -> None:
        with patch("repositories.user_repository.read_query_one", return_value=None):
            self.assertIsNone(get_user_by_id(1))
            self.assertIsNone(get_user_by_username("missing"))

    def test_both_lookups_reject_missing_columns_and_invalid_types(self) -> None:
        cases: list[dict[str, object]] = [
            {key: value for key, value in self.row.items() if key != missing} for missing in self.row
        ]
        invalid_values: list[tuple[str, object]] = [
            ("id", "1"),
            ("id", True),
            ("id", 1.5),
            ("username", 123),
            ("password_hash", 123),
            ("role", "SUPERUSER"),
            ("role", "user"),
            ("token_version", "0"),
            ("token_version", False),
            ("created_at", "2026-01-01T00:00:00"),
        ]
        cases.extend({**self.row, key: value} for key, value in invalid_values)
        cases.extend({**self.row, key: None} for key in self.row)
        for row in cases:
            with self.subTest(row=row), patch("repositories.user_repository.read_query_one", return_value=row):
                with self.assertRaises(ValidationError):
                    get_user_by_id(1)
                with self.assertRaises(ValidationError):
                    get_user_by_username("testuser")

    def test_admin_row_is_accepted(self) -> None:
        admin: UserRow = {**self.row, "role": "ADMIN", "token_version": 3}
        with patch("repositories.user_repository.read_query_one", return_value=admin):
            self.assertEqual(get_user_by_id(1), admin)
            self.assertEqual(get_user_by_username("testuser"), admin)

    def test_create_binds_values_and_defaults_to_user_role(self) -> None:
        with patch("repositories.user_repository.insert_query", return_value=7) as query:
            self.assertEqual(create_user("testuser", "stored-hash"), 7)
        self.assertEqual(query.call_args.args[1], ("testuser", "stored-hash", "USER"))

    def test_writes_return_affected_counts_and_bind_values(self) -> None:
        cases: list[tuple[Callable[[], int], str, tuple[object, ...]]] = [
            (
                lambda: update_password(1, "new-hash"),
                "SET password_hash = ?, token_version = token_version + 1",
                ("new-hash", 1),
            ),
            (lambda: update_role(1, "ADMIN"), "SET role = ?", ("ADMIN", 1)),
            (lambda: update_role(1, "USER"), "SET role = ?", ("USER", 1)),
            (lambda: bump_token_version(1), "SET token_version = token_version + 1", (1,)),
        ]
        for write, statement, params in cases:
            for affected in (0, 1):
                with (
                    self.subTest(statement=statement, affected=affected),
                    patch("repositories.user_repository.write_query", return_value=affected) as query,
                ):
                    self.assertEqual(write(), affected)
                self.assertIn(statement, query.call_args.args[0])
                self.assertIn("WHERE id = ?", query.call_args.args[0])
                self.assertEqual(query.call_args.args[1], params)
                query.assert_called_once()

    def test_create_supports_explicit_admin_role(self) -> None:
        with patch("repositories.user_repository.insert_query", return_value=8) as query:
            self.assertEqual(create_user("admin", "stored-hash", role="ADMIN"), 8)
        sql, params = query.call_args.args
        self.assertIn("INSERT INTO users (username, password_hash, role)", sql)
        self.assertIn("VALUES (?, ?, ?)", sql)
        self.assertEqual(params, ("admin", "stored-hash", "ADMIN"))
        query.assert_called_once()

    def test_lookup_binds_special_and_unicode_usernames(self) -> None:
        for username in ("", "O'Reilly", "' OR 1=1 --", "користувач"):
            with (
                self.subTest(username=username),
                patch("repositories.user_repository.read_query_one", return_value=None) as query,
            ):
                self.assertIsNone(get_user_by_username(username))
            query.assert_called_once_with("SELECT * FROM users WHERE username = ?", (username,))

    def test_create_and_password_update_keep_values_out_of_sql(self) -> None:
        username = "' OR 1=1 --"
        password_hash = "hash'; DROP TABLE users; --"
        with patch("repositories.user_repository.insert_query", return_value=1) as insert:
            create_user(username, password_hash)
        sql, params = insert.call_args.args
        self.assertNotIn(username, sql)
        self.assertNotIn(password_hash, sql)
        self.assertEqual(params, (username, password_hash, "USER"))
        with patch("repositories.user_repository.write_query", return_value=1) as write:
            update_password(1, password_hash)
        sql, params = write.call_args.args
        self.assertNotIn(password_hash, sql)
        self.assertEqual(params, (password_hash, 1))

    def test_lookups_discard_unrecognized_columns_without_mutating_database_row(self) -> None:
        expanded: dict[str, object] = {**self.row, "extra_column": "extra"}
        with patch("repositories.user_repository.read_query_one", return_value=expanded):
            self.assertEqual(get_user_by_id(1), self.row)
            self.assertEqual(get_user_by_username("testuser"), self.row)
        self.assertEqual(expanded["extra_column"], "extra")

    def test_database_errors_propagate_from_every_operation(self) -> None:
        operations: list[tuple[str, Callable[[], object]]] = [
            ("read_query_one", lambda: get_user_by_id(1)),
            ("read_query_one", lambda: get_user_by_username("testuser")),
            ("insert_query", lambda: create_user("testuser", "stored-hash")),
            ("write_query", lambda: update_password(1, "new-hash")),
            ("write_query", lambda: update_role(1, "ADMIN")),
            ("write_query", lambda: bump_token_version(1)),
        ]
        for target, operation in operations:
            error = DatabaseError("Database unavailable")
            with (
                self.subTest(target=target, operation=operation),
                patch(f"repositories.user_repository.{target}", side_effect=error) as query,
                self.assertRaises(DatabaseError) as caught,
            ):
                operation()
            self.assertIs(caught.exception, error)
            query.assert_called_once()

    def test_duplicate_username_error_is_propagated(self) -> None:
        error = DuplicateKeyError("Duplicate username")
        with (
            patch("repositories.user_repository.insert_query", side_effect=error),
            self.assertRaises(DuplicateKeyError) as caught,
        ):
            create_user("testuser", "stored-hash")
        self.assertIs(caught.exception, error)

    def test_password_and_revocation_use_one_statement_and_transaction(self) -> None:
        for failure in (None, "execute", "commit"):
            connection = Mock(spec=database.Connection)
            cursor = Mock(spec=database.Cursor)
            connection.cursor.return_value = cursor
            cursor.rowcount = 1
            if failure == "execute":
                cursor.execute.side_effect = RuntimeError("statement failed")
            elif failure == "commit":
                connection.commit.side_effect = RuntimeError("commit failed")
            with (
                self.subTest(failure=failure),
                patch("data.database._get_db_config", return_value=DBConfig("localhost", "db", "app", "")),
                patch("data.database._get_connection", return_value=connection) as connect,
            ):
                if failure is None:
                    self.assertEqual(update_password(1, "new-hash"), 1)
                    connection.commit.assert_called_once_with()
                    connection.rollback.assert_not_called()
                else:
                    with self.assertLogs("data.database", level="ERROR"), self.assertRaises(DatabaseError):
                        update_password(1, "new-hash")
                    connection.rollback.assert_called_once_with()
                    if failure == "execute":
                        connection.commit.assert_not_called()
            connect.assert_called_once()
            cursor.execute.assert_called_once_with(
                "UPDATE users\nSET password_hash = ?, token_version = token_version + 1\nWHERE id = ?",
                ("new-hash", 1),
            )
            cursor.close.assert_called_once_with()
            connection.close.assert_called_once_with()
