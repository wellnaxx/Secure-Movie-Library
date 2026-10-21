"""Account registration, authentication, token renewal, and account changes.

Callers provide validated request models and enforce permissions. Services hash
passwords, consult current database state, and raise typed errors; HTTP response
mapping belongs to exception_handlers. Multi-step writes commit independently.
"""

from auth.hashing import hash_password, verify_password
from auth.jwt_handler import UserTokenData, create_access_token, create_refresh_token, decode_token
from data.models import (
    RefreshRequest,
    TokenPairResponse,
    UserCreate,
    UserInternal,
    UserPublic,
    UserUpdate,
)
from repositories.user_repository import (
    bump_token_version,
    create_user,
    get_user_by_id,
    get_user_by_username,
    update_password,
    update_role,
)
from utils.errors import (
    DuplicateKeyError,
    IncorrectOldPasswordError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    UserCreationError,
    UsernameAlreadyExistsError,
    UserNotFoundError,
)


def _build_token_payload(user: UserInternal) -> UserTokenData:
    """Select identity, role, and revocation version without the password hash."""
    return {
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "token_version": user.token_version,
    }


def _issue_token_pair(user: UserInternal) -> TokenPairResponse:
    """Sign fresh access and refresh tokens using the user's current state."""
    payload = _build_token_payload(user)

    return TokenPairResponse(
        access_token=create_access_token(payload),
        refresh_token=create_refresh_token(payload),
        token_type="bearer",
    )


def register_user(user_data: UserCreate) -> UserPublic:
    """Hash a password, create a USER account, and return its public profile.

    Raises UsernameAlreadyExistsError for the availability check or a racing
    unique-key conflict. UserCreationError means the committed insert could not
    be reloaded; it does not undo registration. Other repository failures
    propagate unchanged. Registration never accepts an elevated role.
    """
    existing_user = get_user_by_username(user_data.username)
    if existing_user is not None:
        raise UsernameAlreadyExistsError("Username is already taken.")

    password_hash = hash_password(user_data.password)
    try:
        new_user_id = create_user(
            username=user_data.username,
            password_hash=password_hash,
            role="USER",
        )
    except DuplicateKeyError as exc:
        raise UsernameAlreadyExistsError("Username is already taken.") from exc

    created_user = get_user_by_id(new_user_id)
    if created_user is None:
        raise UserCreationError("User was created, but could not be loaded afterwards.")

    return UserPublic.model_validate(created_user)


def authenticate_user(username: str, password: str) -> TokenPairResponse:
    """Verify credentials and issue a token pair without changing account state.

    Missing usernames and incorrect passwords raise InvalidCredentialsError with
    the same public message. Driver and malformed stored-hash errors propagate.
    """
    user_data = get_user_by_username(username)
    if user_data is None:
        raise InvalidCredentialsError("Invalid username or password.")

    user = UserInternal(**user_data)

    if not verify_password(password, user.password_hash):
        raise InvalidCredentialsError("Invalid username or password.")

    return _issue_token_pair(user)


def refresh_token_pair(refresh_request: RefreshRequest) -> TokenPairResponse:
    """Issue a pair from a valid refresh token and current database identity.

    Raises InvalidRefreshTokenError for invalid claims, a deleted account, or a
    token-version mismatch. New tokens use the current role and version. The old
    refresh token remains usable until expiry or a version increment; renewal
    does not rotate or persist individual refresh tokens.
    """
    payload = decode_token(refresh_request.refresh_token, expected_type="refresh")
    if payload is None:
        raise InvalidRefreshTokenError("Invalid or expired refresh token.")

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise InvalidRefreshTokenError("Invalid refresh token payload: missing subject.")

    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError) as exc:
        raise InvalidRefreshTokenError("Invalid refresh token payload: invalid subject.") from exc

    user_data = get_user_by_id(user_id)
    if user_data is None:
        raise InvalidRefreshTokenError("User not found.")

    user = UserInternal(**user_data)

    try:
        token_version = int(payload.get("token_version"))
    except (ValueError, TypeError) as exc:
        raise InvalidRefreshTokenError(
            "Invalid refresh token payload: missing or invalid token_version."
        ) from exc

    if token_version != user.token_version:
        raise InvalidRefreshTokenError("Refresh token has been revoked. Please log in again.")

    return _issue_token_pair(user)


def change_password(current_user: UserInternal, password_data: UserUpdate) -> None:
    """Verify the old password, replace its hash, and revoke prior token pairs.

    Raises IncorrectOldPasswordError before writes if verification fails. The
    hash update and token-version increment are separate committed operations;
    failure of the second does not roll back the first. Request-model validation
    enforces password strength and that the new password differs from the old.
    """
    if not verify_password(password_data.old_password, current_user.password_hash):
        raise IncorrectOldPasswordError("Old password is incorrect.")

    new_password_hash = hash_password(password_data.new_password)

    update_password(current_user.id, new_password_hash)
    bump_token_version(current_user.id)


def update_user_role(user_id: int, role: str) -> UserPublic:
    """Store a caller-validated role and return the reloaded public profile.

    The caller must enforce admin access. UserNotFoundError covers a missing
    account before or after the write. This does not bump token_version: access
    dependencies and token renewal read the current role from the database.
    """
    if get_user_by_id(user_id) is None:
        raise UserNotFoundError("User not found.")

    update_role(user_id, role)

    updated_user = get_user_by_id(user_id)
    if updated_user is None:
        raise UserNotFoundError("User not found after role update.")
    return UserPublic.model_validate(updated_user)
