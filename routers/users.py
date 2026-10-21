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
    """Create a USER account and return its public profile with HTTP 201.

    Registration is public. Existing or concurrently claimed usernames become
    HTTP 409 through the centralized exception handlers.
    """
    return register_user(user_data)


@users_router.post(
    "/login",
    status_code=status.HTTP_200_OK,
)
def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) -> TokenPairResponse:
    """Exchange form-encoded username/password credentials for a bearer pair.

    Invalid credentials produce HTTP 401 with a bearer challenge. The request
    uses application/x-www-form-urlencoded rather than a JSON body.
    """
    return authenticate_user(
        username=form_data.username,
        password=form_data.password,
    )


@users_router.post(
    "/refresh",
    status_code=status.HTTP_200_OK,
)
def refresh(refresh_request: RefreshRequest) -> TokenPairResponse:
    """Exchange a JSON refresh token for a pair after checking account revocation.

    No access token is required. Renewal leaves the submitted refresh token
    valid until its own expiry or a token-version change.
    """
    return refresh_token_pair(refresh_request)


@users_router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
)
def change_user_password(
    password_data: UserUpdate,
    current_user: Annotated[UserInternal, Depends(get_current_user)],
) -> None:
    """Change the authenticated user's password and revoke tokens with HTTP 204.

    The old password must match; request validation checks new-password rules.
    Clients must log in again because the current access token is also revoked.
    """
    change_password(current_user, password_data)


@users_router.get(
    "/me",
    status_code=status.HTTP_200_OK,
)
def me(current_user: Annotated[UserInternal, Depends(get_current_user)]) -> UserPublic:
    """Return the authenticated profile without password hash or token version."""
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
    """Set an account's USER or ADMIN role as an admin and return its profile.

    Missing users produce HTTP 404; role changes apply on the next authenticated
    request because access dependencies reload the current database account.
    """
    return update_user_role(user_id, role_update.role)


@users_router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
def logout(current_user: Annotated[UserInternal, Depends(get_current_user)]) -> None:
    """Increment the account token version and return an empty HTTP 204 response.

    This invalidates all previously issued access and refresh tokens for the
    account, across devices; there is no per-token logout record.
    """
    bump_token_version(current_user.id)
