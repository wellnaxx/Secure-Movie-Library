"""
JWT Token Handler - JSON Web Token operations for authentication.

This module handles creation and validation of JWT tokens for user authentication.
Implements RFC 7519 standard claims for security and interoperability.
"""

import uuid
from datetime import datetime, timezone, timedelta
from jose import JWTError, jwt
from typing import Optional, Literal
from dotenv import load_dotenv
from utils.env_vars import get_env_var

load_dotenv()

ALGORITHM = "HS256"

_SECRET_KEY: str | None = None
_ACCESS_TOKEN_EXPIRE_MINUTES: int | None = None
_REFRESH_TOKEN_EXPIRE_DAYS: int | None = None


def _get_secret_key() -> str:
    """Load and validate the JWT secret key lazily on first use."""
    global _SECRET_KEY
    if _SECRET_KEY is None:
        key = get_env_var("JWT_SECRET_KEY")
        if len(key) < 32:
            raise RuntimeError(
                f"CRITICAL: JWT_SECRET_KEY must be at least 32 characters long for security.\n"
                f"Current length: {len(key)} characters.\n"
                f"Generate a secure key with: openssl rand -hex 32"
            )
        _SECRET_KEY = key
    return _SECRET_KEY


def _get_access_expire_minutes() -> int:
    global _ACCESS_TOKEN_EXPIRE_MINUTES
    if _ACCESS_TOKEN_EXPIRE_MINUTES is None:
        _ACCESS_TOKEN_EXPIRE_MINUTES = int(get_env_var("JWT_EXPIRATION_MINUTES", "30"))
    return _ACCESS_TOKEN_EXPIRE_MINUTES


def _get_refresh_expire_days() -> int:
    global _REFRESH_TOKEN_EXPIRE_DAYS
    if _REFRESH_TOKEN_EXPIRE_DAYS is None:
        _REFRESH_TOKEN_EXPIRE_DAYS = int(get_env_var("JWT_REFRESH_EXPIRATION_DAYS", "7"))
    return _REFRESH_TOKEN_EXPIRE_DAYS


def create_token(data: dict, token_type: Literal["access", "refresh"] = "access") -> str:
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
              Must include: user_id, username, role
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
    token_version = data.get("token_version")
    
    if not user_id:
        raise ValueError("user_id is required in token data")
    if not username:
        raise ValueError("username is required in token data")
    if not role:
        raise ValueError("role is required in token data")
    if token_version is None:
        raise ValueError("token_version is required in token data")
    
    now = datetime.now(timezone.utc)
    expire = now + (timedelta(minutes=_get_access_expire_minutes())
                    if token_type == "access"
                    else timedelta(days=_get_refresh_expire_days()))
    
    payload = {
        "sub": str(user_id),          
        "iat": now,   
        "exp": expire, 
        "jti": str(uuid.uuid4()),     
        
        "type": token_type,            
        "username": data.get("username"),
        "role": data.get("role"),
        "token_version": int(token_version),
    }
    
    encoded_jwt = jwt.encode(payload, _get_secret_key(), algorithm=ALGORITHM)
    
    return encoded_jwt


def decode_token(
    token: str, 
    expected_type: Literal["access", "refresh"] = "access"
) -> Optional[dict]:
    """
    Decode and verify a JWT token.
    
    Validates:
    - Token signature (using SECRET_KEY)
    - Token expiration (exp claim)
    - Token type matches expected type
    
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
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
        
        token_type = payload.get("type")
        if token_type != expected_type:
            return None
        
        return payload
        
    except JWTError:
        return None


def create_access_token(user_data: dict) -> str:
    """
    Create an access token (short-lived).
    
    Convenience wrapper around create_token() for access tokens.
    
    Args:
        user_data: Dict with user_id, username, role
        
    Returns:
        str: Access token
    """
    return create_token(user_data, token_type="access")


def create_refresh_token(user_data: dict) -> str:
    """
    Create a refresh token (long-lived).
    
    Refresh tokens are used to obtain new access tokens without re-authentication.
    They have much longer expiration (typically 7-30 days).
    
    Security Note:
    - Store refresh token hash in database for revocation
    - Implement token rotation on refresh
    - Add revocation mechanism
    
    Args:
        user_data: Dict with user_id, username, role
        
    Returns:
        str: Refresh token
    """
    return create_token(user_data, token_type="refresh")
