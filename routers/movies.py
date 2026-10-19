"""Authenticated movie routes with admin writes and background rating enrichment."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from data.models import SORT_FIELD, SORT_ORDER, MovieCreate, MovieOut, MovieUpdate
from dependencies.auth import get_current_admin, get_current_user
from services.movies_service import (
    create_movie_record,
    delete_movie_record,
    get_movie_record,
    list_movie_records,
    update_movie_record,
)
from services.rating_service import enrich_movie_rating

movies_router = APIRouter(prefix="/movies", tags=["Movies"])


@movies_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_admin)],
)
def create_movie_endpoint(
    movie_data: MovieCreate,
    background_tasks: BackgroundTasks,
) -> MovieOut:
    """Create a movie as an admin and schedule its rating lookup."""
    created_movie = create_movie_record(movie_data)

    background_tasks.add_task(
        enrich_movie_rating,
        created_movie.id,
        created_movie.title,
    )
    return created_movie


@movies_router.get(
    "",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_user)],
)
def list_movies_endpoint(
    q: Annotated[str | None, Query(description="Filter by movie title.")] = None,
    sort_by: SORT_FIELD = "rating",
    order: SORT_ORDER = "desc",
) -> list[MovieOut]:
    """List movies for an authenticated user with validated filter and sort options."""
    return list_movie_records(q=q, sort_by=sort_by, order=order)


@movies_router.get(
    "/{movie_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_user)],
)
def get_movie_endpoint(
    movie_id: int,
) -> MovieOut:
    """Return a movie for an authenticated user, or report a missing record."""
    return get_movie_record(movie_id)


@movies_router.put(
    "/{movie_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_admin)],
)
def update_movie_endpoint(
    movie_id: int,
    movie_data: MovieUpdate,
) -> MovieOut:
    """Apply an admin's movie changes, mapping empty and missing updates to HTTP errors."""
    return update_movie_record(movie_id, movie_data)


@movies_router.delete(
    "/{movie_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_current_admin)],
)
def delete_movie_endpoint(
    movie_id: int,
) -> None:
    """Delete a movie as an admin and return an empty successful response."""
    delete_movie_record(movie_id)
