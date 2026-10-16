"""Parameterized database operations for user accounts and authentication state.

Lookups validate database rows against UserRow without coercing column values.
Writes return generated IDs or affected row counts; database errors propagate to
callers. Password hashing and authorization are handled by the service layer.
"""

from datetime import datetime
from typing import Literal, TypedDict

from pydantic import TypeAdapter

from data.database import insert_query, read_query_one, write_query
from data.queries import QUERIES


class UserRow(TypedDict):
    """User columns returned by the database, including authentication state."""

    id: int
    username: str
    password_hash: str
    role: Literal["ADMIN", "USER"]
    token_version: int
    created_at: datetime


_user_row_adapter: TypeAdapter[UserRow | None] = TypeAdapter(UserRow | None)


def create_user(username: str, password_hash: str, role: str = "USER") -> int:
    """Insert a user with an already hashed password and return the generated ID.

    The role defaults to USER. Database constraints enforce username uniqueness.
    """
    return insert_query(QUERIES.users.create, (username, password_hash, role))


def get_user_by_username(username: str) -> UserRow | None:
    """Return a validated user row, or None when the username is not found.

    Invalid or missing column values raise Pydantic ValidationError.
    """
    return _user_row_adapter.validate_python(
        read_query_one(QUERIES.users.get_by_username, (username,)),
        strict=True,
    )


def get_user_by_id(user_id: int) -> UserRow | None:
    """Return a validated user row, or None when the ID is not found.

    Invalid or missing column values raise Pydantic ValidationError.
    """
    return _user_row_adapter.validate_python(read_query_one(QUERIES.users.get_by_id, (user_id,)), strict=True)


def update_password(user_id: int, password_hash: str) -> int:
    """Store an already hashed password and return the affected row count.

    Token invalidation is a separate operation performed by bump_token_version.
    """
    return write_query(QUERIES.users.update_password, (password_hash, user_id))


def update_role(user_id: int, role: str) -> int:
    """Store a user role and return the affected row count.

    The caller enforces authorization and validates the requested role.
    """
    return write_query(QUERIES.users.update_role, (role, user_id))


def bump_token_version(user_id: int) -> int:
    """Increment the user's token version and return the affected row count.

    Authentication checks reject tokens carrying an older version.
    """
    return write_query(QUERIES.users.bump_token_version, (user_id,))
