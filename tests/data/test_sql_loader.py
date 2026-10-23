"""SQL file loading, caching, and query registry behavior."""

import unittest
from contextlib import chdir
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from data.loader import SQL_DIR, load_sql
from data.queries import MovieQueries, QueryRegistry, UserQueries


class SQLLoaderTests(unittest.TestCase):
    """Read real temporary SQL files to verify loader paths, content, and caching."""

    def setUp(self) -> None:
        """Redirect the loader to an isolated temporary directory and reset its cache on cleanup."""
        directory = TemporaryDirectory(prefix=".tmp_sql_", dir=Path.cwd())
        self.root = Path(directory.name).resolve()
        self.addCleanup(directory.cleanup)
        self.directory_patch = patch("data.loader.SQL_DIR", self.root)
        self.directory_patch.start()
        self.addCleanup(self.directory_patch.stop)
        load_sql.cache_clear()
        self.addCleanup(load_sql.cache_clear)

    def test_loads_utf8_and_strips_surrounding_whitespace(self) -> None:
        path = self.root / "query.sql"
        path.write_text("\n  SELECT 'caf\u00e9'\n\n", encoding="utf-8")
        self.assertEqual(load_sql("query.sql"), "SELECT 'caf\u00e9'")

    def test_successful_reads_are_cached_until_cleared(self) -> None:
        path = self.root / "query.sql"
        path.write_text("SELECT 1", encoding="utf-8")
        self.assertEqual(load_sql("query.sql"), "SELECT 1")
        path.write_text("SELECT 2", encoding="utf-8")
        self.assertEqual(load_sql("query.sql"), "SELECT 1")
        load_sql.cache_clear()
        self.assertEqual(load_sql("query.sql"), "SELECT 2")

    def test_missing_files_have_a_descriptive_error_and_can_be_retried(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "SQL query file not found"):
            load_sql("missing.sql")
        (self.root / "missing.sql").write_text("SELECT 1", encoding="utf-8")
        self.assertEqual(load_sql("missing.sql"), "SELECT 1")

    def test_rejects_empty_files_without_caching_failure(self) -> None:
        path = self.root / "empty.sql"
        path.write_text(" \n\t ", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "SQL query file is empty"):
            load_sql("empty.sql")
        path.write_text("SELECT 1", encoding="utf-8")
        self.assertEqual(load_sql("empty.sql"), "SELECT 1")

    def test_rejects_paths_outside_sql_directory_and_other_extensions(self) -> None:
        for path in ("../outside.sql", str(self.root.parent / "outside.sql"), "query.txt", ""):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "inside the SQL directory"):
                load_sql(path)

    def test_a_directory_is_not_a_query_file(self) -> None:
        (self.root / "directory.sql").mkdir()
        with self.assertRaises(FileNotFoundError):
            load_sql("directory.sql")

    def test_loading_is_independent_of_working_directory(self) -> None:
        nested = self.root / "nested"
        nested.mkdir()
        (self.root / "query.sql").write_text("SELECT 1", encoding="utf-8")
        with chdir(nested):
            self.assertEqual(load_sql("query.sql"), "SELECT 1")


class QueryRegistryTests(unittest.TestCase):
    """Verify lazy independent query groups, immutability, and file registration."""

    def test_construction_does_not_read_sql_files(self) -> None:
        with patch("data.queries.load_sql") as loader:
            QueryRegistry()
        loader.assert_not_called()

    def test_groups_are_independent_and_cached(self) -> None:
        registry = QueryRegistry()
        with patch("data.queries.load_sql", wraps=load_sql) as loader:
            users = registry.users
            self.assertIs(registry.users, users)
            self.assertEqual(loader.call_count, len(fields(UserQueries)))
            self.assertTrue(all(call.args[0].startswith("users/") for call in loader.call_args_list))
            movies = registry.movies
            self.assertIs(registry.movies, movies)
            self.assertEqual(loader.call_count, len(fields(UserQueries)) + len(fields(MovieQueries)))

    def test_missing_group_file_is_reported_and_loading_can_be_retried(self) -> None:
        registry = QueryRegistry()
        with (
            patch("data.queries.load_sql", side_effect=FileNotFoundError("missing query")),
            self.assertRaises(FileNotFoundError),
        ):
            _ = registry.users
        self.assertEqual(registry.users.get_by_id, "SELECT * FROM users WHERE id = ?")

    def test_query_groups_are_immutable(self) -> None:
        registry = QueryRegistry()
        attribute = "create"
        for group in (registry.users, registry.movies):
            with self.subTest(group=type(group).__name__), self.assertRaises(FrozenInstanceError):
                setattr(group, attribute, "replacement")

    def test_all_query_files_are_registered(self) -> None:
        # A new SQL file should be reachable through the typed query catalog.
        registry = QueryRegistry()
        with patch("data.queries.load_sql", wraps=load_sql) as loader:
            _ = registry.users
            _ = registry.movies
        registered = {call.args[0] for call in loader.call_args_list}
        on_disk = {path.relative_to(SQL_DIR).as_posix() for path in SQL_DIR.rglob("*.sql")}
        self.assertEqual(registered, on_disk)
