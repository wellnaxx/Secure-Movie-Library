"""
JWT Token Handler - JSON Web Token operations for authentication.

This module handles creation and validation of JWT tokens for user authentication.
Implements RFC 7519 standard claims for security and interoperability.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal, TypedDict

from jose import JWTError, jwt
from pydantic import TypeAdapter, ValidationError

from config.jwt import get_jwt_config

ALGORITHM = "HS256"


class UserTokenData(TypedDict):
    """User information required to issue access and refresh tokens."""

    user_id: int
    username: str
    role: Literal["USER", "ADMIN"]
    token_version: int


class JWTPayload(TypedDict):
    """JWT claims; encoding converts datetime values to Unix timestamps."""

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

    Args:
        data: Dictionary containing user information.
              Must include: user_id, username, role, token_version
        token_type: Type of token to create ("access" or "refresh")

    Returns:
        str: Encoded JWT token

    Raises:
        ValueError: If user_id is missing from data

    Example:
        >>> token_data = {"user_id": 123, "username": "johndoe", "role": "USER"}
        >>> token = create_token(token_data)
        >>> print(token)
        'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...'
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
    - Token signature (using SECRET_KEY)
    - Token expiration (exp claim)
    - Token type matches expected type
    - Required payload claims have the expected types

    Args:
        token: JWT token string to decode
        expected_type: Expected token type ("access" or "refresh")

    Returns:
        dict: Token payload if valid, containing:
              - sub: User ID (as string)
              - iat: Issued at timestamp
              - exp: Expiration timestamp
              - jti: Unique token ID
              - type: Token type
              - username: User's username
              - role: User's role
        None: If token is invalid, expired, malformed, or wrong type

    Example:
        >>> payload = decode_token(access_token, expected_type="access")
        >>> if payload:
        ...     user_id = int(payload["sub"])
        ...     print(f"Valid token for user {user_id}")
        ... else:
        ...     print("Invalid or expired token")
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

    Refresh tokens are used to obtain new access tokens without re-authentication.
    They have much longer expiration (typically 7-30 days).

    Security Note:
    - Store refresh token hash in database for revocation
    - Implement token rotation on refresh
    - Add revocation mechanism

    Args:
        user_data: Dict with user_id, username, role, token_version

    Returns:
        str: Refresh token
    """
    return create_token(user_data, token_type="refresh")
