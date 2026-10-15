# Unit tests intentionally exercise private parsing and HTTP helpers.
# pyright: reportPrivateUsage=false

import unittest
from contextlib import AbstractContextManager
from unittest.mock import AsyncMock, MagicMock, patch

from config.omdb import OMDbConfig
from services.rating_service import (
    _fetch_rating_from_omdb,
    _parse_omdb_rating,
    enrich_movie_rating,
)


class TestParseOmdbRating(unittest.TestCase):
    def test_returns_float_for_valid_rating(self) -> None:
        self.assertEqual(_parse_omdb_rating({"imdbRating": "8.8"}), 8.8)

    def test_returns_none_for_na_string(self) -> None:
        self.assertIsNone(_parse_omdb_rating({"imdbRating": "N/A"}))

    def test_returns_none_for_empty_string(self) -> None:
        self.assertIsNone(_parse_omdb_rating({"imdbRating": ""}))

    def test_returns_none_when_key_missing(self) -> None:
        self.assertIsNone(_parse_omdb_rating({}))

    def test_returns_none_for_non_numeric_value(self) -> None:
        self.assertIsNone(_parse_omdb_rating({"imdbRating": "great"}))

    def test_returns_none_when_rating_below_zero(self) -> None:
        self.assertIsNone(_parse_omdb_rating({"imdbRating": "-1.0"}))

    def test_returns_none_when_rating_above_ten(self) -> None:
        self.assertIsNone(_parse_omdb_rating({"imdbRating": "10.1"}))

    def test_returns_zero_at_lower_boundary(self) -> None:
        self.assertEqual(_parse_omdb_rating({"imdbRating": "0.0"}), 0.0)

    def test_returns_ten_at_upper_boundary(self) -> None:
        self.assertEqual(_parse_omdb_rating({"imdbRating": "10.0"}), 10.0)


# ---------------------------------------------------------------------------
# Helpers for async HTTP mocking
# ---------------------------------------------------------------------------


def _make_async_client(mock_response: MagicMock) -> MagicMock:
    """
    Return a mock that satisfies `async with httpx.AsyncClient() as client:`.
    mock_response is what client.get() will return.
    """
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    # Support `async with` on the AsyncClient() instance
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _mock_config() -> AbstractContextManager[MagicMock]:
    return patch(
        "services.rating_service.get_omdb_config",
        return_value=OMDbConfig(api_key="testkey"),
    )


class TestFetchRatingFromOmdb(unittest.IsolatedAsyncioTestCase):
    async def test_http_request_uses_typed_configuration(self) -> None:
        response = MagicMock()
        response.json.return_value = {"Response": "True", "imdbRating": "8.8"}
        context = _make_async_client(response)
        config = OMDbConfig(api_key="custom-key", base_url="https://example.com/api", timeout_seconds=2.5)
        with (
            patch("services.rating_service.httpx.AsyncClient", return_value=context),
            patch("services.rating_service.get_omdb_config", return_value=config),
        ):
            self.assertEqual(await _fetch_rating_from_omdb("Example"), (8.8, None))
        context.__aenter__.return_value.get.assert_awaited_once_with(
            "https://example.com/api",
            params={"apikey": "custom-key", "t": "Example"},
            timeout=2.5,
        )

    async def test_returns_rating_on_successful_response(self) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"Response": "True", "imdbRating": "8.8"}
        mock_resp.raise_for_status.return_value = None

        with (
            patch("services.rating_service.httpx.AsyncClient", return_value=_make_async_client(mock_resp)),
            _mock_config(),
        ):
            rating, error = await _fetch_rating_from_omdb("Inception")

        self.assertEqual(rating, 8.8)
        self.assertIsNone(error)

    async def test_returns_none_rating_and_error_when_omdb_says_false(self) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"Response": "False", "Error": "Movie not found!"}
        mock_resp.raise_for_status.return_value = None

        with (
            patch("services.rating_service.httpx.AsyncClient", return_value=_make_async_client(mock_resp)),
            _mock_config(),
        ):
            rating, error = await _fetch_rating_from_omdb("Unknown Movie")

        self.assertIsNone(rating)
        self.assertEqual(error, "Movie not found!")

    async def test_returns_error_message_on_timeout(self) -> None:
        import httpx as httpx_mod

        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=httpx_mod.TimeoutException("timed out"))
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_client)
        cm.__aexit__ = AsyncMock(return_value=False)

        with patch("services.rating_service.httpx.AsyncClient", return_value=cm), _mock_config():
            rating, error = await _fetch_rating_from_omdb("Inception")

        self.assertIsNone(rating)
        if error is None:
            self.fail("Expected a timeout error")
        self.assertIn("timed out", error.lower())

    async def test_returns_error_on_http_status_error(self) -> None:
        import httpx as httpx_mod

        mock_response = httpx_mod.Response(401)
        exc = httpx_mod.HTTPStatusError("401 Unauthorized", request=MagicMock(), response=mock_response)

        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=exc)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_client)
        cm.__aexit__ = AsyncMock(return_value=False)

        with patch("services.rating_service.httpx.AsyncClient", return_value=cm), _mock_config():
            rating, error = await _fetch_rating_from_omdb("Inception")

        self.assertIsNone(rating)
        if error is None:
            self.fail("Expected an HTTP status error")
        self.assertIn("401", error)

    async def test_returns_none_rating_when_imdb_rating_is_na(self) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"Response": "True", "imdbRating": "N/A"}
        mock_resp.raise_for_status.return_value = None

        with (
            patch("services.rating_service.httpx.AsyncClient", return_value=_make_async_client(mock_resp)),
            _mock_config(),
        ):
            rating, error = await _fetch_rating_from_omdb("Obscure Film")

        self.assertIsNone(rating)
        self.assertIsNone(error)


class TestEnrichMovieRating(unittest.IsolatedAsyncioTestCase):
    @patch("services.rating_service.update_movie_rating")
    @patch("services.rating_service._fetch_rating_from_omdb", new_callable=AsyncMock)
    async def test_persists_rating_on_success(self, mock_fetch: AsyncMock, mock_update: MagicMock) -> None:
        mock_fetch.return_value = (8.8, None)

        await enrich_movie_rating(1, "Inception")

        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args.kwargs
        self.assertEqual(call_kwargs["movie_id"], 1)
        self.assertEqual(call_kwargs["rating"], 8.8)
        self.assertIsNone(call_kwargs["enrichment_error"])
        self.assertEqual(call_kwargs["source"], "OMDb")

    @patch("services.rating_service.update_movie_rating")
    @patch("services.rating_service._fetch_rating_from_omdb", new_callable=AsyncMock)
    async def test_persists_error_when_fetch_returns_error(
        self, mock_fetch: AsyncMock, mock_update: MagicMock
    ) -> None:
        mock_fetch.return_value = (None, "Movie not found!")

        await enrich_movie_rating(1, "Unknown Movie")

        call_kwargs = mock_update.call_args.kwargs
        self.assertIsNone(call_kwargs["rating"])
        self.assertEqual(call_kwargs["enrichment_error"], "Movie not found!")

    @patch("services.rating_service.update_movie_rating")
    @patch("services.rating_service._fetch_rating_from_omdb", new_callable=AsyncMock)
    async def test_persists_none_rating_when_imdb_rating_absent(
        self, mock_fetch: AsyncMock, mock_update: MagicMock
    ) -> None:
        mock_fetch.return_value = (None, None)

        await enrich_movie_rating(1, "Obscure Film")

        call_kwargs = mock_update.call_args.kwargs
        self.assertIsNone(call_kwargs["rating"])
        self.assertIsNone(call_kwargs["enrichment_error"])

    @patch("services.rating_service.update_movie_rating")
    @patch("services.rating_service._fetch_rating_from_omdb", new_callable=AsyncMock)
    async def test_does_not_raise_when_update_movie_rating_fails(
        self, mock_fetch: AsyncMock, mock_update: MagicMock
    ) -> None:
        mock_fetch.return_value = (8.8, None)
        mock_update.side_effect = Exception("DB is down")

        # Should not propagate the exception
        await enrich_movie_rating(1, "Inception")


if __name__ == "__main__":
    unittest.main()
