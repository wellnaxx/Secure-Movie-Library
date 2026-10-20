"""
JWT Token Handler - JSON Web Token operations for authentication.

Signs HS256 access and refresh tokens using the shared configured secret. Decode
checks signatures, expiration, expected token type, and the typed claim shape.
Account existence, current role, and token-version revocation are checked against
the database by authentication dependencies and the refresh service, not here.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal, TypedDict

from jose import JWTError, jwt
from pydantic import TypeAdapter, ValidationError

from config.jwt import get_jwt_config

ALGORITHM = "HS256"


class UserTokenData(TypedDict):
    """Identity and current database token version required to issue a token.

    Password hashes are never included. role is copied into the signed token,
    while authorization still reloads the user's current database role.
    """

    user_id: int
    username: str
    role: Literal["USER", "ADMIN"]
    token_version: int


class JWTPayload(TypedDict):
    """Required signed claims, including token purpose and revocation version.

    sub contains the user ID as text; jti is a UUID token identifier. Encoding
    converts UTC datetime values for iat/exp into Unix timestamps. Successful
    decoding validates every field without coercion before returning this shape.
    """

    sub: str
    iat: datetime | int
    exp: datetime | int
    jti: str
    type: Literal["access", "refresh"]
    username: str
    role: Literal["USER", "ADMIN"]
    token_version: int


_jwt_payload_adapter: TypeAdapter[JWTPayload] = TypeAdapter(JWTPayload)


def create_token(data: UserTokenData, token_type: Literal["access", "refresh"] = "access") -> str:
    """
    Create a JWT token with standard RFC 7519 claims.

    Standard Claims Included:
    - sub (subject): User ID who the token is for
    - iat (issued at): When the token was created
    - exp (expiration): When the token expires
    - jti (JWT ID): Unique identifier for this token

    Custom Claims:
    - type: "access" or "refresh" to prevent token confusion
    - username: User's username
    - role: User's role (USER or ADMIN)
    - token_version: Database version used to revoke previously issued tokens

    Args:
        data: Dictionary containing user information.
              Must include: user_id, username, role, token_version
        token_type: Type of token to create ("access" or "refresh")

    Returns:
        str: Encoded JWT token

    Raises:
        ValueError: If user_id, username, or role is empty, or token_version
            cannot be converted to an integer.
        KeyError: If token_version is missing from a runtime dictionary.
        OSError: If a required environment setting is unavailable.
        RuntimeError: If the configured signing secret is too short.

    Example:
        >>> token_data: UserTokenData = {
        ...     "user_id": 123, "username": "johndoe", "role": "USER", "token_version": 0
        ... }
        >>> token = create_token(token_data)
    """
    user_id = data.get("user_id")
    username = data.get("username")
    role = data.get("role")
    token_version = data["token_version"]

    if not user_id:
        raise ValueError("user_id is required in token data")
    if not username:
        raise ValueError("username is required in token data")
    if not role:
        raise ValueError("role is required in token data")

    config = get_jwt_config()
    now = datetime.now(UTC)
    expire = now + (
        timedelta(minutes=config.access_token_expire_minutes)
        if token_type == "access"
        else timedelta(days=config.refresh_token_expire_days)
    )

    payload: JWTPayload = {
        "sub": str(user_id),
        "iat": now,
        "exp": expire,
        "jti": str(uuid.uuid4()),
        "type": token_type,
        "username": username,
        "role": role,
        "token_version": int(token_version),
    }

    return jwt.encode(dict(payload), config.secret_key, algorithm=ALGORITHM)


def decode_token(token: str, expected_type: Literal["access", "refresh"] = "access") -> JWTPayload | None:
    """
    Decode and verify a JWT token.

    Validates:
    - Token signature (using the configured JWT_SECRET_KEY and HS256)
    - Token expiration (exp claim)
    - Token type matches expected type
    - Required payload claims have the expected types

    Args:
        token: JWT token string to decode
        expected_type: Expected token type ("access" or "refresh")

    Returns:
        JWTPayload: Token payload if valid, containing:
              - sub: User ID (as string)
              - iat: Issued at timestamp
              - exp: Expiration timestamp
              - jti: Unique token ID
              - type: Token type
              - username: User's username
              - role: User's role
              - token_version: Account revocation version at issuance
        None: If token is invalid, expired, malformed, or wrong type

    Configuration failures propagate rather than being reported as invalid
    tokens. This function does not check account existence or revocation state.
    """
    config = get_jwt_config()
    try:
        decoded = jwt.decode(token, config.secret_key, algorithms=[ALGORITHM])
        payload = _jwt_payload_adapter.validate_python(decoded, strict=True)
    except (JWTError, ValidationError):
        return None
    else:
        token_type = payload.get("type")
        if token_type != expected_type:
            return None
        return payload


def create_access_token(user_data: UserTokenData) -> str:
    """
    Create an access token (short-lived).

    Convenience wrapper around create_token() for access tokens.

    Args:
        user_data: Dict with user_id, username, role, token_version

    Returns:
        str: Access token
    """
    return create_token(user_data, token_type="access")


def create_refresh_token(user_data: UserTokenData) -> str:
    """
    Create a refresh token (long-lived).

    Lifetime comes from JWTConfig.refresh_token_expire_days (seven by default).
    Refresh tokens share the access-token signing key and carry type="refresh".
    Revocation compares token_version with the current account; individual token
    hashes are not stored and renewal does not rotate or revoke the old token.

    Args:
        user_data: Dict with user_id, username, role, token_version

    Returns:
        str: Refresh token
    """
    return create_token(user_data, token_type="refresh")
