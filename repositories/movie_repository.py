from datetime import datetime
from decimal import Decimal
from typing import TypedDict

from pydantic import TypeAdapter

from data.database import insert_query, read_query, read_query_one, write_query
from data.models import MovieUpdateFields


class MovieRow(TypedDict):
    """Movie columns returned by MariaDB, including its decimal rating value."""

    id: int
    title: str
    director: str | None
    release_year: int | None
    rating: Decimal | float | None
    rating_source: str | None
    rating_updated_at: datetime | None
    enrichment_error: str | None
    created_at: datetime
    updated_at: datetime


_movie_rows_adapter: TypeAdapter[list[MovieRow]] = TypeAdapter(list[MovieRow])
_optional_movie_row_adapter: TypeAdapter[MovieRow | None] = TypeAdapter(MovieRow | None)


def create_movie(title: str, director: str | None, release_year: int | None) -> int:
    """
    Insert a new movie record and return the new row's id.
    """

    sql = """
        INSERT INTO movies (title, director, release_year)
        VALUES (?, ?, ?)
    """
    return insert_query(sql, (title, director, release_year))

def list_movies(
    q: str | None = None,
    sort_by: str = "rating",
    order: str = "desc",
) -> list[MovieRow]:
    """
    List movies with optional title filter and safe sorting.

    - q: substring match on title (case-insensitive depending on collation; utf8mb4_unicode_ci is CI)
    - sort_by: one of: rating, title, release_year, created_at
    - order: asc|desc
    """

    sort_columns = {
        "rating": "rating",
        "title": "title",
        "release_year": "release_year",
        "created_at": "created_at",
    }

    sort_col = sort_columns.get(sort_by, "rating")
    direction = "ASC" if str(order).lower() == "asc" else "DESC"

    where_sql = ""
    params: list[str] = []

    if q:
        where_sql = "WHERE title LIKE ?"
        params.append(f"%{q.strip()}%")

    if sort_col == "rating":
        order_sql = f"ORDER BY (rating IS NULL) ASC, rating {direction}, id ASC"
    else:
        order_sql = f"ORDER BY {sort_col} {direction}, id ASC"

    sql = f"""
        SELECT
            id, title, director, release_year,
            rating, rating_source, rating_updated_at,
            enrichment_error, created_at, updated_at
        FROM movies
        {where_sql}
        {order_sql}
    """

    return _movie_rows_adapter.validate_python(read_query(sql, tuple(params)), strict=True)


def get_movie(movie_id: int) -> MovieRow | None:
    """
    Fetch a single movie by id. Returns None if no matching record exists.
    """

    sql = "SELECT * FROM movies WHERE id = ?"
    return _optional_movie_row_adapter.validate_python(read_query_one(sql, (movie_id,)), strict=True)


def update_movie(movie_id: int, fields: MovieUpdateFields) -> int:
    """
    Update a movie record with the given fields.

    fields is a dict of column_name -> value produced by MovieUpdate.fields_to_update().
    Only keys defined by MovieUpdateFields ("title", "director", "release_year")
    are accepted — invalid column names are caught at type-check time, not at runtime.
    Values may be None, which sets the column to NULL in the database.
    An empty dict is a no-op and returns 0.

    Returns the number of affected rows.
    """

    if not fields:
        return 0

    updates = [f"{col} = ?" for col in fields]
    params: list[object] = list(fields.values())
    params.append(movie_id)

    sql = f"""
        UPDATE movies
        SET {", ".join(updates)}
        WHERE id = ?
    """

    return write_query(sql, tuple(params))


def update_movie_rating(
    movie_id: int,
    rating: float | None,
    source: str | None,
    updated_at: datetime | None,
    enrichment_error: str | None = None,
) -> int:
    """
    Persist the result of a rating enrichment attempt.

    Sets rating, rating_source, rating_updated_at, and enrichment_error on the
    given movie record. Pass rating=None and a non-None enrichment_error to record
    a failed enrichment. Returns the number of affected rows.
    """

    sql = """
        UPDATE movies
        SET rating = ?, rating_source = ?, rating_updated_at = ?, enrichment_error = ?
        WHERE id = ?
    """

    return write_query(
        sql,
        (rating, source, updated_at, enrichment_error, movie_id),
    )


def delete_movie(movie_id: int) -> int:
    """
    Delete a movie by id. Returns the number of affected rows (0 if not found).
    """
    sql = "DELETE FROM movies WHERE id = ?"
    return write_query(sql, (movie_id,))
