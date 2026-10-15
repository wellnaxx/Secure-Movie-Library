import unittest
from unittest.mock import Mock, patch

from data import database
from utils.errors import DatabaseError


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
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
