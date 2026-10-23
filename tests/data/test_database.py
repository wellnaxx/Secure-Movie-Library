"""Database-helper contracts using mocked cursors and connections, without a live server."""

import unittest
from unittest.mock import Mock, patch

from data import database
from utils.errors import DatabaseError, DuplicateKeyError, RepositoryError


class DriverError(Exception):
    """MariaDB-style error metadata without requiring the native driver in tests."""

    def __init__(self, errno: int | None, sqlstate: str | None, message: str = "driver details") -> None:
        """Attach driver error metadata while retaining a private diagnostic message."""
        super().__init__(message)
        self.errno = errno
        self.sqlstate = sqlstate


class DatabaseTests(unittest.TestCase):
    """Verify query results, commits, rollback, cleanup, and typed error translation."""

    def setUp(self) -> None:
        """Provide driver-spec mocks and register cleanup for every connection/config patch."""
        self.cursor = Mock(spec=database.Cursor)
        self.connection = Mock(spec=database.Connection)
        self.connection.cursor.return_value = self.cursor
        self.cursor.description = [("id",), ("title",)]
        self.config = database.DBConfig("localhost", "movies", "user", "password")
        self.addCleanup(patch.stopall)
        patch("data.database._get_db_config", return_value=self.config).start()
        self.connection_patch = patch("data.database._get_connection", return_value=self.connection)
        self.connection_patch.start()

    def test_read_maps_column_names_and_closes_resources(self) -> None:
        self.cursor.fetchall.return_value = [(1, "Example")]
        self.assertEqual(database.read_query("SELECT id, title"), [{"id": 1, "title": "Example"}])
        self.cursor.close.assert_called_once_with()
        self.connection.close.assert_called_once_with()

    def test_debug_logging_does_not_include_bound_parameter_values(self) -> None:
        secret = "sensitive-password-hash"
        self.cursor.fetchall.return_value = [(1, "Example")]
        self.cursor.fetchone.return_value = (1, "Example")
        self.cursor.lastrowid = 1
        self.cursor.rowcount = 1
        with self.assertLogs("data.database", level="DEBUG") as captured:
            database.read_query("SELECT id, title WHERE password_hash = ?", (secret,))
            database.read_query_one("SELECT id, title WHERE password_hash = ?", (secret,))
            database.insert_query("INSERT INTO users (password_hash) VALUES (?)", (secret,))
            database.write_query("UPDATE users SET password_hash = ?", (secret,))
        self.assertEqual(len(captured.records), 4)
        self.assertNotIn(secret, " ".join(captured.output))

    def test_connection_uses_typed_database_configuration(self) -> None:
        self.connection_patch.stop()
        driver = Mock()
        driver.connect.return_value = self.connection
        self.cursor.fetchone.return_value = (1, "Example")
        config = database.DBConfig("db.example", "catalog", "app", "secret", port=3307, connect_timeout=12)
        with (
            patch("data.database.import_module", return_value=driver),
            patch("data.database._get_db_config", return_value=config),
        ):
            self.assertEqual(database.read_query_one("SELECT id, title"), {"id": 1, "title": "Example"})
        driver.connect.assert_called_once_with(
            user="app",
            password="secret",
            host="db.example",
            port=3307,
            database="catalog",
            connect_timeout=12,
        )

    def test_read_one_returns_none_when_no_rows_match(self) -> None:
        self.cursor.fetchone.return_value = None
        self.assertIsNone(database.read_query_one("SELECT id, title"))
        self.cursor.close.assert_called_once_with()
        self.connection.close.assert_called_once_with()

    def test_missing_metadata_raises_database_error_and_closes_resources(self) -> None:
        self.cursor.description = None
        with self.assertLogs("data.database", level="ERROR"), self.assertRaises(DatabaseError):
            database.read_query("SELECT id, title")
        self.cursor.close.assert_called_once_with()
        self.connection.close.assert_called_once_with()

    def test_insert_commits_and_returns_generated_id(self) -> None:
        self.cursor.lastrowid = 7
        self.assertEqual(database.insert_query("INSERT INTO movies VALUES (?)", ("Example",)), 7)
        self.cursor.execute.assert_called_once_with("INSERT INTO movies VALUES (?)", ("Example",))
        self.connection.commit.assert_called_once_with()
        self.connection.rollback.assert_not_called()
        self.cursor.close.assert_called_once_with()
        self.connection.close.assert_called_once_with()

    def test_missing_insert_id_rolls_back_before_commit(self) -> None:
        self.cursor.lastrowid = None
        with self.assertLogs("data.database", level="ERROR"), self.assertRaises(DatabaseError):
            database.insert_query("INSERT INTO movies VALUES (?)", ("Example",))
        self.connection.commit.assert_not_called()
        self.connection.rollback.assert_called_once_with()
        self.cursor.close.assert_called_once_with()
        self.connection.close.assert_called_once_with()

    def test_write_failure_rolls_back_and_closes_resources(self) -> None:
        self.cursor.execute.side_effect = RuntimeError("query failed")
        with self.assertLogs("data.database", level="ERROR"), self.assertRaises(DatabaseError):
            database.write_query("DELETE FROM movies")
        self.connection.commit.assert_not_called()
        self.connection.rollback.assert_called_once_with()
        self.cursor.close.assert_called_once_with()
        self.connection.close.assert_called_once_with()

    def test_duplicate_inserts_and_updates_raise_typed_conflicts(self) -> None:
        for write in (database.insert_query, database.write_query):
            self.cursor.reset_mock()
            self.connection.reset_mock()
            error = DriverError(1062, "23000", "private duplicate value")
            self.cursor.execute.side_effect = error
            with (
                self.subTest(write=write),
                self.assertNoLogs("data.database", level="ERROR"),
                self.assertRaises(DuplicateKeyError) as caught,
            ):
                write("write statement", ("sensitive value",))
            self.assertIsInstance(caught.exception, RepositoryError)
            self.assertIs(caught.exception.__cause__, error)
            self.assertNotIn("private duplicate value", str(caught.exception))
            self.connection.commit.assert_not_called()
            self.connection.rollback.assert_called_once_with()
            self.cursor.close.assert_called_once_with()
            self.connection.close.assert_called_once_with()

    def test_other_driver_failures_do_not_become_duplicate_errors(self) -> None:
        for code, state in (
            (1452, "23000"),
            (1048, "23000"),
            (1064, "42000"),
            (2002, "HY000"),
            (1062, "HY000"),
            (None, None),
        ):
            for write in (database.insert_query, database.write_query):
                self.cursor.reset_mock()
                self.connection.reset_mock()
                error = DriverError(code, state, "duplicate key private driver details")
                self.cursor.execute.side_effect = error
                with (
                    self.subTest(code=code, state=state, write=write),
                    self.assertLogs("data.database", level="ERROR"),
                    self.assertRaises(DatabaseError) as caught,
                ):
                    write("write statement")
                self.assertNotIsInstance(caught.exception, DuplicateKeyError)
                self.assertIs(caught.exception.__cause__, error)
                self.assertNotIn("private driver details", str(caught.exception))
                self.connection.rollback.assert_called_once_with()
                self.cursor.close.assert_called_once_with()
                self.connection.close.assert_called_once_with()

    def test_read_failures_are_wrapped_with_their_original_cause(self) -> None:
        for read in (database.read_query, database.read_query_one):
            self.cursor.reset_mock()
            self.connection.reset_mock()
            error = DriverError(2002, "HY000", "private connection details")
            self.cursor.execute.side_effect = error
            with (
                self.subTest(read=read),
                self.assertLogs("data.database"),
                self.assertRaises(DatabaseError) as caught,
            ):
                read("read statement")
            self.assertIsInstance(caught.exception, RepositoryError)
            self.assertIs(caught.exception.__cause__, error)
            self.assertNotIn("private connection details", str(caught.exception))
            self.connection.rollback.assert_not_called()
            self.cursor.close.assert_called_once_with()
            self.connection.close.assert_called_once_with()

    def test_existing_repository_errors_are_preserved(self) -> None:
        for operation in (
            database.read_query,
            database.read_query_one,
            database.insert_query,
            database.write_query,
        ):
            for error in (DatabaseError("already classified"), DuplicateKeyError("already classified")):
                self.cursor.execute.side_effect = error
                with (
                    self.subTest(operation=operation, error=type(error).__name__),
                    self.assertRaises(type(error)) as caught,
                    patch("data.database.logger"),
                ):
                    operation("statement")
                self.assertIs(caught.exception, error)
                self.assertIsNone(caught.exception.__cause__)
