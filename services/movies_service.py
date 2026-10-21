"""Movie business operations, returning public schemas and typed service errors.

Repositories own SQL and row validation. These functions enforce operation-level
rules; routers enforce access permissions and schedule enrichment separately.
Repository and Pydantic validation failures propagate to the HTTP handlers.
"""

from data.models import MovieCreate, MovieOut, MovieUpdate
from repositories.movie_repository import (
    create_movie,
    delete_movie,
    get_movie,
    list_movies,
    update_movie,
)
from utils.errors import EmptyMovieUpdateError, MovieCreationError, MovieDeleteError, MovieNotFoundError


def create_movie_record(movie_data: MovieCreate) -> MovieOut:
    """
    Create a movie in the database and return the created record.
    Rating enrichment is triggered separately by the router as a background task.
    """
    new_movie_id = create_movie(
        title=movie_data.title,
        director=movie_data.director,
        release_year=movie_data.release_year,
    )

    created_movie = get_movie(new_movie_id)
    if created_movie is None:
        raise MovieCreationError("Movie was created, but could not be loaded afterwards.")

    return MovieOut.model_validate(created_movie)


def list_movie_records(
    q: str | None = None,
    sort_by: str = "rating",
    order: str = "desc",
) -> list[MovieOut]:
    """Return public movies using the repository's filter and sorting rules.

    An empty catalog or unmatched title filter returns an empty list. Internal
    enrichment errors are excluded when the returned models are serialized.
    """
    return [MovieOut.model_validate(movie) for movie in list_movies(q=q, sort_by=sort_by, order=order)]


def get_movie_record(movie_id: int) -> MovieOut:
    """Return one public movie, raising MovieNotFoundError when absent."""
    movie = get_movie(int(movie_id))
    if movie is None:
        raise MovieNotFoundError("Movie not found.")

    return MovieOut.model_validate(movie)


def update_movie_record(movie_id: int, movie_data: MovieUpdate) -> MovieOut:
    """Apply supplied fields and reload the movie without rerunning enrichment.

    Raises EmptyMovieUpdateError before database access for an empty update, or
    MovieNotFoundError if the row is absent before or after the write. Nullable
    fields explicitly supplied as None are cleared. The read/write/read sequence
    uses separate connections and is not a single transaction.
    """
    fields = movie_data.fields_to_update()
    if not fields:
        raise EmptyMovieUpdateError("No fields were provided for update.")

    existing_movie = get_movie(movie_id)
    if existing_movie is None:
        raise MovieNotFoundError("Movie not found.")

    update_movie(movie_id=movie_id, fields=fields)

    updated_movie = get_movie(movie_id)
    if updated_movie is None:
        raise MovieNotFoundError("Movie not found after update.")

    return MovieOut.model_validate(updated_movie)


def delete_movie_record(movie_id: int) -> None:
    """Delete an existing movie or raise a typed operation error.

    An absent initial lookup raises MovieNotFoundError; a subsequent delete that
    affects no rows raises MovieDeleteError, including a concurrent deletion.
    """
    existing_movie = get_movie(movie_id)
    if existing_movie is None:
        raise MovieNotFoundError("Movie not found.")

    affected_rows = delete_movie(movie_id)
    if affected_rows == 0:
        raise MovieDeleteError("Movie could not be deleted.")
