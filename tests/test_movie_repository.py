import unittest
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import patch

from pydantic import ValidationError

from repositories.movie_repository import (
    MovieRow,
    create_movie,
    delete_movie,
    get_movie,
    list_movies,
    update_movie,
    update_movie_rating,
)
from utils.errors import DatabaseError

if TYPE_CHECKING:
    from collections.abc import Callable

    from data.models import MovieUpdateFields


class MovieRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.row: MovieRow = {
            "id": 1,
            "title": "Example",
            "director": None,
            "release_year": 2020,
            "rating": Decimal("8.50"),
            "rating_source": "OMDb",
            "rating_updated_at": None,
            "enrichment_error": None,
            "created_at": datetime(2026, 1, 1),
            "updated_at": datetime(2026, 1, 1),
        }

    def test_list_validates_rows_and_preserves_decimal_ratings(self) -> None:
        with patch("repositories.movie_repository.read_query", return_value=[self.row]):
            rows = list_movies()
        self.assertEqual(rows, [self.row])
        self.assertIsInstance(rows[0]["rating"], Decimal)

    def test_get_returns_none_for_missing_movie(self) -> None:
        with patch("repositories.movie_repository.read_query_one", return_value=None):
            self.assertIsNone(get_movie(1))

    def test_get_rejects_missing_required_columns(self) -> None:
        incomplete: dict[str, object] = {key: value for key, value in self.row.items() if key != "title"}
        with (
            patch("repositories.movie_repository.read_query_one", return_value=incomplete),
            self.assertRaises(ValidationError),
        ):
            get_movie(1)

    def test_list_rejects_invalid_column_types_without_coercion(self) -> None:
        malformed: dict[str, object] = {**self.row, "id": "1"}
        with (
            patch("repositories.movie_repository.read_query", return_value=[malformed]),
            self.assertRaises(ValidationError),
        ):
            list_movies()

    def test_get_returns_valid_movie_and_binds_id(self) -> None:
        with patch("repositories.movie_repository.read_query_one", return_value=self.row) as query:
            self.assertEqual(get_movie(7), self.row)
        query.assert_called_once_with("SELECT * FROM movies WHERE id = ?", (7,))

    def test_list_handles_empty_results_and_optional_values(self) -> None:
        nullable: MovieRow = {**self.row, "release_year": None, "rating": None, "rating_source": None}
        for rows in ([], [nullable]):
            with self.subTest(rows=rows), patch("repositories.movie_repository.read_query", return_value=rows):
                self.assertEqual(list_movies(), rows)

    def test_list_supports_sort_columns_and_directions(self) -> None:
        for column in ("rating", "title", "release_year", "created_at"):
            for order in ("asc", "ASC", "desc"):
                with (
                    self.subTest(column=column, order=order),
                    patch("repositories.movie_repository.read_query", return_value=[]) as query,
                ):
                    list_movies(sort_by=column, order=order)
                sql, params = query.call_args.args
                direction = "ASC" if order.lower() == "asc" else "DESC"
                prefix = "(rating IS NULL) ASC, " if column == "rating" else ""
                self.assertIn(f"ORDER BY {prefix}{column} {direction}, id ASC", sql)
                self.assertEqual(params, ())

    def test_list_falls_back_for_unsafe_sort_inputs(self) -> None:
        unsafe = "title; DROP TABLE movies"
        with patch("repositories.movie_repository.read_query", return_value=[]) as query:
            list_movies(sort_by=unsafe, order=unsafe)
        sql, params = query.call_args.args
        self.assertIn("ORDER BY (rating IS NULL) ASC, rating DESC, id ASC", sql)
        self.assertNotIn(unsafe, sql)
        self.assertEqual(params, ())

    def test_list_binds_search_text_and_handles_blank_filters(self) -> None:
        cases = ((None, ()), ("", ()), ("   ", ("%%",)), ("  ' OR 1=1 --  ", ("%' OR 1=1 --%",)))
        for search, expected in cases:
            with (
                self.subTest(search=search),
                patch("repositories.movie_repository.read_query", return_value=[]) as query,
            ):
                list_movies(q=search)
            sql, params = query.call_args.args
            self.assertEqual(params, expected)
            self.assertEqual("WHERE title LIKE ?" in sql, bool(search))
            self.assertNotIn("' OR 1=1 --", sql)

    def test_create_binds_movie_values_and_returns_id(self) -> None:
        for director, year in ((None, None), ("Director", 2020)):
            with (
                self.subTest(director=director, year=year),
                patch("repositories.movie_repository.insert_query", return_value=7) as query,
            ):
                self.assertEqual(create_movie("Example", director, year), 7)
            sql, params = query.call_args.args
            self.assertIn("VALUES (?, ?, ?)", sql)
            self.assertEqual(params, ("Example", director, year))

    def test_empty_update_does_not_query_database(self) -> None:
        with patch("repositories.movie_repository.write_query") as query:
            self.assertEqual(update_movie(1, {}), 0)
        query.assert_not_called()

    def test_update_rejects_untrusted_column_names_before_querying(self) -> None:
        update_unchecked: Callable[..., int] = update_movie
        for column in ("rating", "title = NULL; DROP TABLE movies; --"):
            with (
                self.subTest(column=column),
                patch("repositories.movie_repository.write_query") as query,
                self.assertRaisesRegex(ValueError, "Unsupported movie update column"),
            ):
                update_unchecked(1, {column: "value"})
            query.assert_not_called()

    def test_update_binds_values_in_column_order_and_allows_nulls(self) -> None:
        fields: MovieUpdateFields = {"title": "'quoted title'", "director": None, "release_year": None}
        for affected in (0, 1):
            with (
                self.subTest(affected=affected),
                patch("repositories.movie_repository.write_query", return_value=affected) as query,
            ):
                self.assertEqual(update_movie(7, fields), affected)
            sql, params = query.call_args.args
            self.assertIn("SET title = ?, director = ?, release_year = ?", sql)
            self.assertNotIn("'quoted title'", sql)
            self.assertEqual(params, ("'quoted title'", None, None, 7))

    def test_rating_updates_persist_success_and_failure(self) -> None:
        timestamp = datetime(2026, 1, 1)
        for rating, source, error in ((8.5, "OMDb", None), (None, None, "Movie not found in OMDb.")):
            with (
                self.subTest(rating=rating, error=error),
                patch("repositories.movie_repository.write_query", return_value=1) as query,
            ):
                self.assertEqual(update_movie_rating(7, rating, source, timestamp, error), 1)
            self.assertEqual(query.call_args.args[1], (rating, source, timestamp, error, 7))

    def test_delete_returns_affected_count_and_binds_id(self) -> None:
        for affected in (0, 1):
            with (
                self.subTest(affected=affected),
                patch("repositories.movie_repository.write_query", return_value=affected) as query,
            ):
                self.assertEqual(delete_movie(7), affected)
            query.assert_called_once_with("DELETE FROM movies WHERE id = ?", (7,))

    def test_database_errors_propagate_from_all_repository_operations(self) -> None:
        operations: list[tuple[str, Callable[[], object]]] = [
            ("read_query", list_movies),
            ("read_query_one", lambda: get_movie(1)),
            ("insert_query", lambda: create_movie("Example", None, None)),
            ("write_query", lambda: update_movie(1, {"title": "Updated"})),
            ("write_query", lambda: update_movie_rating(1, None, None, None)),
            ("write_query", lambda: delete_movie(1)),
        ]
        for target, operation in operations:
            error = DatabaseError("Database unavailable")
            with (
                self.subTest(target=target, operation=operation),
                patch(f"repositories.movie_repository.{target}", side_effect=error),
                self.assertRaises(DatabaseError) as caught,
            ):
                operation()
            self.assertIs(caught.exception, error)
