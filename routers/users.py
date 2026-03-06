from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from data.models import (
    RefreshRequest,
    TokenPairResponse,
    UserCreate,
    UserInternal,
    UserPublic,
    UserUpdate,
    UserRoleUpdate,
)
from dependencies.auth import get_current_user, get_current_admin
from services.user_service import (
    authenticate_user,
    change_password,
    get_current_user_public_profile,
    refresh_token_pair,
    register_user,
    update_user_role
)

from utils.errors import (
    UsernameAlreadyExistsError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    UserNotFoundError,
    IncorrectOldPasswordError,
)


users_router = APIRouter(prefix="/users", tags=["Authentication"])


@users_router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
)
def register(user_data: UserCreate) -> UserPublic:
    try:
        return register_user(user_data)
    except UsernameAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@users_router.post(
    "/login",
    response_model=TokenPairResponse,
    status_code=status.HTTP_200_OK,
)
def login(form_data: OAuth2PasswordRequestForm = Depends()) -> TokenPairResponse:
    try:
        return authenticate_user(
            username=form_data.username,
            password=form_data.password,
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@users_router.post(
    "/refresh",
    response_model=TokenPairResponse,
    status_code=status.HTTP_200_OK,
)
def refresh(refresh_request: RefreshRequest) -> TokenPairResponse:
    try:
        return refresh_token_pair(refresh_request)
    except InvalidRefreshTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@users_router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
)
def change_user_password(
    password_data: UserUpdate,
    current_user: UserInternal = Depends(get_current_user),
) -> None:
    try:
        change_password(current_user, password_data)
        return None
    except IncorrectOldPasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@users_router.get(
    "/me",
    response_model=UserPublic,
    status_code=status.HTTP_200_OK,
)
def me(current_user: UserInternal = Depends(get_current_user)) -> UserPublic:
    try:
        return get_current_user_public_profile(current_user)
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    
@users_router.patch("/{user_id}/role", response_model=UserPublic)
def set_user_role(
    user_id: int,
    role_update: UserRoleUpdate,
    current_admin: UserInternal = Depends(get_current_admin),
) -> UserPublic:
    try:
        return update_user_role(user_id, role_update.role)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
