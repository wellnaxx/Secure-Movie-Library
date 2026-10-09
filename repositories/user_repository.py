from datetime import datetime
from typing import Literal, TypedDict, cast

from data.database import insert_query, read_query_one, write_query


class UserRow(TypedDict):
    """User columns returned by the database, including authentication state."""

    id: int
    username: str
    password_hash: str
    role: Literal["ADMIN", "USER"]
    token_version: int
    created_at: datetime


def create_user(username: str, password_hash: str, role: str = "USER") -> int:
    sql = """
        INSERT INTO users (username, password_hash, role)
        VALUES (?, ?, ?)
    """
    return insert_query(sql, (username, password_hash, role))


def get_user_by_username(username: str) -> UserRow | None:
    sql = "SELECT * FROM users WHERE username = ?"
    return cast("UserRow | None", read_query_one(sql, (username,)))


def get_user_by_id(user_id: int) -> UserRow | None:
    sql = "SELECT * FROM users WHERE id = ?"
    return cast("UserRow | None", read_query_one(sql, (user_id,)))


def update_password(user_id: int, password_hash: str) -> int:
    sql = """
        UPDATE users
        SET password_hash = ?
        WHERE id = ?
    """
    return write_query(sql, (password_hash, user_id))


def update_role(user_id: int, role: str) -> int:
    sql = """
        UPDATE users
        SET role = ?
        WHERE id = ?
    """
    return write_query(sql, (role, user_id))


def bump_token_version(user_id: int) -> int:
    sql = """
        UPDATE users
        SET token_version = token_version + 1
        WHERE id = ?
    """
    return write_query(sql, (user_id,))
