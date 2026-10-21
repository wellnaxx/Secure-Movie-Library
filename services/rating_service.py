"""Best-effort OMDb enrichment run in the API process after movie creation.

Normal HTTP/API failures become stored enrichment errors. The background entry
point logs unexpected fetch and persistence errors so they do not undo creation.
There is no durable task queue, retry policy, or automatic title-change refresh.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from config.omdb import get_omdb_config
from repositories.movie_repository import update_movie_rating

logger = logging.getLogger(__name__)


class RatingServiceError(Exception):
    """Base error for rating enrichment."""


def _parse_omdb_rating(response_data: dict[str, Any]) -> float | None:
    """
    Extract a usable numeric rating from OMDb response data.

    Preferred source:
    - imdbRating

    Returns None if rating is missing or invalid.
    """
    raw_rating = response_data.get("imdbRating")

    if raw_rating in (None, "N/A", ""):
        return None

    try:
        rating = float(raw_rating)
    except (TypeError, ValueError):
        return None

    return rating if 0 <= rating <= 10 else None


async def _fetch_rating_from_omdb(title: str) -> tuple[float | None, str | None]:
    """
    Fetch movie data from OMDb by title and return:

    - rating (float | None)
    - enrichment_error (str | None)

    Timeouts, HTTP failures, transport errors, and invalid JSON return an error
    message. An absent or unusable rating in an otherwise successful response
    returns (None, None). Configuration errors and unexpected response shapes
    propagate to the background task's safety net. The title is sent as the
    OMDb ``t`` query parameter; this function does not write to the database.
    """
    config = get_omdb_config()

    params = {
        "apikey": config.api_key,
        "t": title,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(config.base_url, params=params, timeout=config.timeout_seconds)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        return None, "OMDb request timed out."
    except httpx.HTTPStatusError as exc:
        return None, f"OMDb HTTP error: {exc.response.status_code}."
    except httpx.RequestError as exc:
        return None, f"OMDb request failed: {exc}."
    except ValueError:
        return None, "OMDb returned invalid JSON."

    if data.get("Response") == "False":
        error_message = data.get("Error", "Movie not found in OMDb.")
        return None, error_message

    rating = _parse_omdb_rating(data)
    return rating, None


async def enrich_movie_rating(movie_id: int, title: str) -> None:
    """
    Background task: fetch rating from OMDb and update the local movie record.

    This function is intentionally safe:
    - it does not raise for expected external/API failures
    - it logs failures
    - it stores enrichment_error when appropriate
    """
    logger.info("Starting rating enrichment for movie_id=%s title=%r", movie_id, title)

    rating: float | None = None
    enrichment_error: str | None = None

    try:
        rating, enrichment_error = await _fetch_rating_from_omdb(title)
    except Exception as exc:  # pragma: no cover
        # Last-resort safety net so background task never crashes the app flow
        logger.exception(
            "Unexpected error during rating enrichment for movie_id=%s",
            movie_id,
        )
        enrichment_error = f"Unexpected enrichment error: {exc}"

    try:
        update_movie_rating(
            movie_id=movie_id,
            rating=rating,
            source="OMDb",
            updated_at=datetime.now(UTC),
            enrichment_error=enrichment_error,
        )
    except Exception:  # pragma: no cover
        logger.exception(
            "Failed to persist rating enrichment result for movie_id=%s",
            movie_id,
        )
        return

    logger.info(
        "Finished rating enrichment for movie_id=%s rating=%s error=%r",
        movie_id,
        rating,
        enrichment_error,
    )
