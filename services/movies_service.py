from data.models import MovieCreate, MovieOut, MovieUpdate
from repositories.movie_repository import (
    create_movie,
    delete_movie,
    get_movie,
    list_movies,
    update_movie,
)

from utils.errors import (
    MovieCreationError,
    MovieNotFoundError,
    MovieUpdateError,
    EmptyMovieUpdateError,
    MovieDeleteError
)


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

    return MovieOut(**created_movie)


def list_movie_records(
    q: str | None = None,
    sort_by: str = "rating",
    order: str = "desc",
) -> list[MovieOut]:
    return [MovieOut(**movie) for movie in list_movies(q=q, sort_by=sort_by, order=order)]


def get_movie_record(movie_id: int) -> MovieOut:
    movie = get_movie(int(movie_id))
    if movie is None:
        raise MovieNotFoundError("Movie not found.")

    return MovieOut(**movie)


def update_movie_record(movie_id: int, movie_data: MovieUpdate) -> MovieOut:
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

    return MovieOut(**updated_movie)


def delete_movie_record(movie_id: int) -> None:
    existing_movie = get_movie(movie_id)
    if existing_movie is None:
        raise MovieNotFoundError("Movie not found.")

    affected_rows = delete_movie(movie_id)
    if affected_rows == 0:
        raise MovieDeleteError("Movie could not be deleted.")