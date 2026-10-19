"""User and authentication endpoints; HTTP failures are mapped centrally."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from data.models import (
    RefreshRequest,
    TokenPairResponse,
    UserCreate,
    UserInternal,
    UserPublic,
    UserRoleUpdate,
    UserUpdate,
)
from dependencies.auth import get_current_admin, get_current_user
from repositories.user_repository import bump_token_version
from services.user_service import (
    authenticate_user,
    change_password,
    refresh_token_pair,
    register_user,
    update_user_role,
)

users_router = APIRouter(prefix="/users", tags=["Authentication"])


@users_router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
)
def register(user_data: UserCreate) -> UserPublic:
    return register_user(user_data)


@users_router.post(
    "/login",
    status_code=status.HTTP_200_OK,
)
def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) -> TokenPairResponse:
    return authenticate_user(
        username=form_data.username,
        password=form_data.password,
    )


@users_router.post(
    "/refresh",
    status_code=status.HTTP_200_OK,
)
def refresh(refresh_request: RefreshRequest) -> TokenPairResponse:
    return refresh_token_pair(refresh_request)


@users_router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
)
def change_user_password(
    password_data: UserUpdate,
    current_user: Annotated[UserInternal, Depends(get_current_user)],
) -> None:
    change_password(current_user, password_data)


@users_router.get(
    "/me",
    status_code=status.HTTP_200_OK,
)
def me(current_user: Annotated[UserInternal, Depends(get_current_user)]) -> UserPublic:
    return UserPublic(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        created_at=current_user.created_at,
    )


@users_router.patch(
    "/{user_id}/role", status_code=status.HTTP_200_OK, dependencies=[Depends(get_current_admin)]
)
def set_user_role(
    user_id: int,
    role_update: UserRoleUpdate,
) -> UserPublic:
    return update_user_role(user_id, role_update.role)


@users_router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
def logout(current_user: Annotated[UserInternal, Depends(get_current_user)]) -> None:
    bump_token_version(current_user.id)
