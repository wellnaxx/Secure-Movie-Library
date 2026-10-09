from data.models import (
    RefreshRequest,
    TokenPairResponse,
    UserCreate,
    UserInternal,
    UserPublic,
    UserUpdate,
)
from auth.hashing import hash_password, verify_password
from auth.jwt_handler import UserTokenData, create_access_token, create_refresh_token, decode_token
from repositories.user_repository import (
    bump_token_version,
    create_user,
    get_user_by_id,
    get_user_by_username,
    update_password,
    update_role
)

from utils.errors import (
    UsernameAlreadyExistsError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    UserNotFoundError,
    IncorrectOldPasswordError,
)


def _build_token_payload(user: UserInternal) -> UserTokenData:
    return {
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "token_version": user.token_version,
    }


def _issue_token_pair(user: UserInternal) -> TokenPairResponse:
    payload = _build_token_payload(user)

    return TokenPairResponse(
        access_token=create_access_token(payload),
        refresh_token=create_refresh_token(payload),
        token_type="bearer",
    )


def register_user(user_data: UserCreate) -> UserPublic:
    existing_user = get_user_by_username(user_data.username)
    if existing_user is not None:
        raise UsernameAlreadyExistsError("Username is already taken.")

    password_hash = hash_password(user_data.password)
    new_user_id = create_user(
        username=user_data.username,
        password_hash=password_hash,
        role="USER",
    )

    created_user = get_user_by_id(new_user_id)
    if created_user is None:
        raise UserNotFoundError("User was created, but could not be loaded afterwards.")

    return UserPublic(**created_user)


def authenticate_user(username: str, password: str) -> TokenPairResponse:
    user_data = get_user_by_username(username)
    if user_data is None:
        raise InvalidCredentialsError("Invalid username or password.")

    user = UserInternal(**user_data)

    if not verify_password(password, user.password_hash):
        raise InvalidCredentialsError("Invalid username or password.")

    return _issue_token_pair(user)


def refresh_token_pair(refresh_request: RefreshRequest) -> TokenPairResponse:
    payload = decode_token(refresh_request.refresh_token, expected_type="refresh")
    if payload is None:
        raise InvalidRefreshTokenError("Invalid or expired refresh token.")

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise InvalidRefreshTokenError("Invalid refresh token payload: missing subject.")

    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        raise InvalidRefreshTokenError("Invalid refresh token payload: invalid subject.")

    user_data = get_user_by_id(user_id)
    if user_data is None:
        raise UserNotFoundError("User not found.")

    user = UserInternal(**user_data)

    try:
        token_version = int(payload.get("token_version"))
    except (ValueError, TypeError):
        raise InvalidRefreshTokenError(
            "Invalid refresh token payload: missing or invalid token_version."
        )

    if token_version != user.token_version:
        raise InvalidRefreshTokenError(
            "Refresh token has been revoked. Please log in again."
        )

    return _issue_token_pair(user)


def change_password(current_user: UserInternal, password_data: UserUpdate) -> None:
    if not verify_password(password_data.old_password, current_user.password_hash):
        raise IncorrectOldPasswordError("Old password is incorrect.")

    new_password_hash = hash_password(password_data.new_password)

    update_password(current_user.id, new_password_hash)
    bump_token_version(current_user.id)


def update_user_role(user_id: int, role: str) -> UserPublic:
    if get_user_by_id(user_id) is None:
        raise UserNotFoundError("User not found.")

    update_role(user_id, role)
    
    updated_user = get_user_by_id(user_id)
    if updated_user is None:
        raise UserNotFoundError("User not found after role update.")
    return UserPublic(**updated_user)
