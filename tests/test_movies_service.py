import unittest
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

from services.movies_service import (
    create_movie_record,
    delete_movie_record,
    get_movie_record,
    list_movie_records,
    update_movie_record,
)
from utils.errors import (
    EmptyMovieUpdateError,
    MovieCreationError,
    MovieDeleteError,
    MovieNotFoundError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _movie_dict(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": 1,
        "title": "Inception",
        "director": "Christopher Nolan",
        "release_year": 2010,
        "rating": 8.8,
        "rating_source": "OMDb",
        "rating_updated_at": datetime(2024, 1, 1),
        "created_at": datetime(2024, 1, 1),
        "updated_at": datetime(2024, 1, 1),
    }
    base.update(overrides)
    return base


def _movie_update(**fields: Any) -> MagicMock:
    """Build a MovieUpdate-like mock with fields_to_update() returning fields."""
    m = MagicMock()
    m.fields_to_update.return_value = fields
    return m


class TestCreateMovieRecord(unittest.TestCase):
    @patch("services.movies_service.get_movie")
    @patch("services.movies_service.create_movie")
    def test_returns_movie_out_on_success(self, mock_create: MagicMock, mock_get: MagicMock) -> None:
        mock_create.return_value = 1
        mock_get.return_value = _movie_dict()

        from data.models import MovieCreate

        result = create_movie_record(
            MovieCreate(title="Inception", director="Christopher Nolan", release_year=2010)
        )

        mock_create.assert_called_once_with(title="Inception", director="Christopher Nolan", release_year=2010)
        mock_get.assert_called_once_with(1)
        self.assertEqual(result.id, 1)
        self.assertEqual(result.title, "Inception")

    @patch("services.movies_service.get_movie")
    @patch("services.movies_service.create_movie")
    def test_raises_movie_creation_error_when_get_returns_none(
        self, mock_create: MagicMock, mock_get: MagicMock
    ) -> None:
        mock_create.return_value = 99
        mock_get.return_value = None

        from data.models import MovieCreate

        with self.assertRaises(MovieCreationError):
            create_movie_record(MovieCreate(title="Ghost Movie"))


class TestGetMovieRecord(unittest.TestCase):
    @patch("services.movies_service.get_movie")
    def test_returns_movie_out_when_found(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _movie_dict()
        result = get_movie_record(1)
        self.assertEqual(result.id, 1)
        self.assertEqual(result.title, "Inception")

    @patch("services.movies_service.get_movie")
    def test_raises_movie_not_found_when_missing(self, mock_get: MagicMock) -> None:
        mock_get.return_value = None
        with self.assertRaises(MovieNotFoundError):
            get_movie_record(404)


class TestListMovieRecords(unittest.TestCase):
    @patch("services.movies_service.list_movies")
    def test_returns_list_of_movie_out(self, mock_list: MagicMock) -> None:
        mock_list.return_value = [_movie_dict(), _movie_dict(id=2, title="The Matrix")]
        result = list_movie_records()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].title, "Inception")
        self.assertEqual(result[1].title, "The Matrix")

    @patch("services.movies_service.list_movies")
    def test_passes_query_params_to_repository(self, mock_list: MagicMock) -> None:
        mock_list.return_value = []
        list_movie_records(q="nolan", sort_by="title", order="asc")
        mock_list.assert_called_once_with(q="nolan", sort_by="title", order="asc")

    @patch("services.movies_service.list_movies")
    def test_returns_empty_list_when_no_movies(self, mock_list: MagicMock) -> None:
        mock_list.return_value = []
        self.assertEqual(list_movie_records(), [])


class TestUpdateMovieRecord(unittest.TestCase):
    @patch("services.movies_service.get_movie")
    @patch("services.movies_service.update_movie")
    def test_updates_title_successfully(self, mock_update: MagicMock, mock_get: MagicMock) -> None:
        mock_get.side_effect = [_movie_dict(), _movie_dict(title="Inception (2010)")]
        mock_update.return_value = 1

        result = update_movie_record(1, _movie_update(title="Inception (2010)"))

        mock_update.assert_called_once_with(movie_id=1, fields={"title": "Inception (2010)"})
        self.assertEqual(result.title, "Inception (2010)")

    @patch("services.movies_service.get_movie")
    @patch("services.movies_service.update_movie")
    def test_clears_director_when_explicitly_null(self, mock_update: MagicMock, mock_get: MagicMock) -> None:
        """director=None in fields means set to NULL in DB."""
        mock_get.side_effect = [_movie_dict(), _movie_dict(director=None)]
        mock_update.return_value = 1

        result = update_movie_record(1, _movie_update(director=None))

        mock_update.assert_called_once_with(movie_id=1, fields={"director": None})
        self.assertIsNone(result.director)

    @patch("services.movies_service.get_movie")
    @patch("services.movies_service.update_movie")
    def test_clears_release_year_when_explicitly_null(
        self, mock_update: MagicMock, mock_get: MagicMock
    ) -> None:
        """release_year=None in fields means set to NULL in DB."""
        mock_get.side_effect = [_movie_dict(), _movie_dict(release_year=None)]
        mock_update.return_value = 1

        update_movie_record(1, _movie_update(release_year=None))

        call_fields = mock_update.call_args.kwargs["fields"]
        self.assertIn("release_year", call_fields)
        self.assertIsNone(call_fields["release_year"])

    @patch("services.movies_service.get_movie")
    @patch("services.movies_service.update_movie")
    def test_omitted_fields_not_included_in_update(self, mock_update: MagicMock, mock_get: MagicMock) -> None:
        """Sending only title must not touch director or release_year."""
        mock_get.side_effect = [_movie_dict(), _movie_dict(title="New Title")]
        mock_update.return_value = 1

        update_movie_record(1, _movie_update(title="New Title"))

        call_fields = mock_update.call_args.kwargs["fields"]
        self.assertIn("title", call_fields)
        self.assertNotIn("director", call_fields)
        self.assertNotIn("release_year", call_fields)

    def test_raises_empty_update_error_when_no_fields_provided(self) -> None:
        with self.assertRaises(EmptyMovieUpdateError):
            update_movie_record(1, _movie_update())  # empty dict from fields_to_update

    @patch("services.movies_service.get_movie")
    def test_raises_movie_not_found_when_movie_missing(self, mock_get: MagicMock) -> None:
        mock_get.return_value = None
        with self.assertRaises(MovieNotFoundError):
            update_movie_record(999, _movie_update(title="Anything"))

    @patch("services.movies_service.get_movie")
    @patch("services.movies_service.update_movie")
    def test_raises_movie_not_found_if_record_vanishes_after_update(
        self, mock_update: MagicMock, mock_get: MagicMock
    ) -> None:
        mock_get.side_effect = [_movie_dict(), None]
        mock_update.return_value = 1
        with self.assertRaises(MovieNotFoundError):
            update_movie_record(1, _movie_update(title="Anything"))


class TestDeleteMovieRecord(unittest.TestCase):
    @patch("services.movies_service.delete_movie")
    @patch("services.movies_service.get_movie")
    def test_deletes_successfully(self, mock_get: MagicMock, mock_delete: MagicMock) -> None:
        mock_get.return_value = _movie_dict()
        mock_delete.return_value = 1
        delete_movie_record(1)  # should not raise
        mock_delete.assert_called_once_with(1)

    @patch("services.movies_service.get_movie")
    def test_raises_movie_not_found_when_movie_missing(self, mock_get: MagicMock) -> None:
        mock_get.return_value = None
        with self.assertRaises(MovieNotFoundError):
            delete_movie_record(999)

    @patch("services.movies_service.delete_movie")
    @patch("services.movies_service.get_movie")
    def test_raises_movie_delete_error_when_zero_rows_affected(
        self, mock_get: MagicMock, mock_delete: MagicMock
    ) -> None:
        mock_get.return_value = _movie_dict()
        mock_delete.return_value = 0
        with self.assertRaises(MovieDeleteError):
            delete_movie_record(1)


if __name__ == "__main__":
    unittest.main()
