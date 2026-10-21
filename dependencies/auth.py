"""
FastAPI dependencies for authentication and authorization.
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from auth.jwt_handler import decode_token
from data.models import UserInternal
from repositories.user_repository import get_user_by_id
from utils.errors import AuthorizationError, InvalidAccessTokenError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/login")


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> UserInternal:
    """
    Validate the JWT access token and return the authenticated user.

    Invalid, expired, or revoked tokens and deleted users raise
    InvalidAccessTokenError, mapped centrally to HTTP 401.

    Current identity, role, password hash, and version come from the database;
    signed role claims do not grant permissions after a role change. Missing
    bearer credentials are handled by OAuth2PasswordBearer before this runs.
    Repository failures propagate as server failures, not authentication errors.
    """
    payload = decode_token(token, expected_type="access")
    if payload is None:
        raise InvalidAccessTokenError("Invalid or expired token.")

    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        raise InvalidAccessTokenError("Invalid token payload: missing subject (sub) claim.")

    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError) as exc:
        raise InvalidAccessTokenError("Invalid token payload: subject must be a valid user ID.") from exc

    user_data = get_user_by_id(user_id)
    if user_data is None:
        raise InvalidAccessTokenError("User not found. Account may have been deleted.")

    user = UserInternal(**user_data)

    try:
        token_version = int(payload.get("token_version"))
    except (ValueError, TypeError) as exc:
        raise InvalidAccessTokenError("Invalid token payload: missing or invalid token_version.") from exc

    if token_version != user.token_version:
        raise InvalidAccessTokenError("Token revoked. Please log in again.")

    return user


def get_current_admin(
    current_user: Annotated[UserInternal, Depends(get_current_user)],
) -> UserInternal:
    """Require ADMIN role; AuthorizationError is mapped centrally to HTTP 403."""
    if current_user.role != "ADMIN":
        raise AuthorizationError("This operation requires administrator privileges.")
    return current_user
