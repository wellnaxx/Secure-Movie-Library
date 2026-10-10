"""Parameterized database operations for user accounts and authentication state.

Lookups validate database rows against UserRow without coercing column values.
Writes return generated IDs or affected row counts; database errors propagate to
callers. Password hashing and authorization are handled by the service layer.
"""

from datetime import datetime
from typing import Literal, TypedDict

from pydantic import TypeAdapter

from data.database import insert_query, read_query_one, write_query


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
    sql = """
        INSERT INTO users (username, password_hash, role)
        VALUES (?, ?, ?)
    """
    return insert_query(sql, (username, password_hash, role))


def get_user_by_username(username: str) -> UserRow | None:
    """Return a validated user row, or None when the username is not found.

    Invalid or missing column values raise Pydantic ValidationError.
    """
    sql = "SELECT * FROM users WHERE username = ?"
    return _user_row_adapter.validate_python(read_query_one(sql, (username,)), strict=True)


def get_user_by_id(user_id: int) -> UserRow | None:
    """Return a validated user row, or None when the ID is not found.

    Invalid or missing column values raise Pydantic ValidationError.
    """
    sql = "SELECT * FROM users WHERE id = ?"
    return _user_row_adapter.validate_python(read_query_one(sql, (user_id,)), strict=True)


def update_password(user_id: int, password_hash: str) -> int:
    """Store an already hashed password and return the affected row count.

    Token invalidation is a separate operation performed by bump_token_version.
    """
    sql = """
        UPDATE users
        SET password_hash = ?
        WHERE id = ?
    """
    return write_query(sql, (password_hash, user_id))


def update_role(user_id: int, role: str) -> int:
    """Store a user role and return the affected row count.

    The caller enforces authorization and validates the requested role.
    """
    sql = """
        UPDATE users
        SET role = ?
        WHERE id = ?
    """
    return write_query(sql, (role, user_id))


def bump_token_version(user_id: int) -> int:
    """Increment the user's token version and return the affected row count.

    Authentication checks reject tokens carrying an older version.
    """
    sql = """
        UPDATE users
        SET token_version = token_version + 1
        WHERE id = ?
    """
    return write_query(sql, (user_id,))
