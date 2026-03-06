from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from data.models import MovieCreate, MovieOut, MovieUpdate, UserInternal
from dependencies.auth import get_current_admin, get_current_user
from services.movies_service import (
    EmptyMovieUpdateError,
    MovieCreationError,
    MovieDeleteError,
    MovieNotFoundError,
    MovieUpdateError,
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
    response_model=MovieOut,
    status_code=status.HTTP_201_CREATED,
)
def create_movie_endpoint(
    movie_data: MovieCreate,
    background_tasks: BackgroundTasks,
    current_admin: UserInternal = Depends(get_current_admin),
) -> MovieOut:
    try:
        created_movie = create_movie_record(movie_data)

        background_tasks.add_task(
            enrich_movie_rating,
            created_movie.id,
            created_movie.title,
        )

        return created_movie
    except MovieCreationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@movies_router.get(
    "",
    response_model=list[MovieOut],
    status_code=status.HTTP_200_OK,
)
def list_movies_endpoint(
    q: str | None = Query(default=None, description="Filter by movie title."),
    sort_by: str = Query(default="rating", pattern="^(rating|title|release_year|created_at)$"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    current_user: UserInternal = Depends(get_current_user),
) -> list[MovieOut]:
    return list_movie_records(q=q, sort_by=sort_by, order=order)


@movies_router.get(
    "/{movie_id}",
    response_model=MovieOut,
    status_code=status.HTTP_200_OK,
)
def get_movie_endpoint(
    movie_id: int,
    current_user: UserInternal = Depends(get_current_user),
) -> MovieOut:
    try:
        return get_movie_record(movie_id)
    except MovieNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@movies_router.put(
    "/{movie_id}",
    response_model=MovieOut,
    status_code=status.HTTP_200_OK,
)
def update_movie_endpoint(
    movie_id: int,
    movie_data: MovieUpdate,
    current_admin: UserInternal = Depends(get_current_admin),
) -> MovieOut:
    try:
        return update_movie_record(movie_id, movie_data)
    except EmptyMovieUpdateError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except MovieNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except MovieUpdateError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@movies_router.delete(
    "/{movie_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_movie_endpoint(
    movie_id: int,
    current_admin: UserInternal = Depends(get_current_admin),
) -> None:
    try:
        delete_movie_record(movie_id)
        return None
    except MovieNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except MovieDeleteError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc