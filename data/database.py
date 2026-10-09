"""
database.py - Low-level database access layer.

All read functions return dicts keyed by column name so callers always
access results by name, never by positional index.

Public API
----------
read_query(sql, params)     -> list[dict]
read_query_one(sql, params) -> dict | None
insert_query(sql, params)   -> int   (last inserted row id)
write_query(sql, params)    -> int   (affected row count)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING, Any, Protocol, cast

from dotenv import load_dotenv

from utils.env_vars import get_env_var
from utils.errors import DatabaseError

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

logger = logging.getLogger(__name__)

load_dotenv()

class Cursor(Protocol):
    """Database cursor operations used by this module."""

    @property
    def description(self) -> Sequence[tuple[str, *tuple[Any, ...]]] | None: ...

    @property
    def lastrowid(self) -> int | None: ...

    @property
    def rowcount(self) -> int: ...

    def execute(self, statement: str, data: tuple[Any, ...] = ()) -> None: ...

    def fetchall(self) -> Sequence[Sequence[Any]]: ...

    def fetchone(self) -> Sequence[Any] | None: ...

    def close(self) -> None: ...


class Connection(Protocol):
    """Database connection operations used by this module."""

    def cursor(self) -> Cursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class DBConfig:
    host: str
    name: str
    user: str
    password: str
    port: int = 3306
    connect_timeout: int = 5


def load_db_config() -> DBConfig:
    return DBConfig(
        host=get_env_var("DB_HOST"),
        name=get_env_var("DB_NAME"),
        user=get_env_var("DB_USER"),
        password=get_env_var("DB_PASSWORD"),
        port=int(get_env_var("DB_PORT", "3306")),
        connect_timeout=int(get_env_var("DB_CONNECT_TIMEOUT", "5")),
    )


_db_config: DBConfig | None = None


def _get_db_config() -> DBConfig:
    """Return the DB config, loading it lazily on first use."""
    global _db_config
    if _db_config is None:
        _db_config = load_db_config()
    return _db_config


def set_db_config(config: DBConfig) -> None:
    """Override DB config (useful for tests)."""
    global _db_config
    _db_config = config


def _get_connection(config: DBConfig) -> Connection:
    """Create a new DB connection.

    Imports the MariaDB driver lazily so unit tests that mock repositories can
    run without requiring a native DB connector.
    """
    try:
        driver = import_module("mariadb")
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise DatabaseError(
            "MariaDB driver not installed. Install 'mariadb' (and the system C connector) to run the app."
        ) from exc

    # MariaDB's annotations are incomplete; type its interface at this boundary.
    connect_driver = cast("Callable[..., Connection]", driver.connect)
    return connect_driver(
        user=config.user,
        password=config.password,
        host=config.host,
        port=config.port,
        database=config.name,
        connect_timeout=config.connect_timeout,
    )


def _cursor_columns(cursor: Cursor) -> list[str]:
    """Return column names for a cursor with a result set."""
    description = cursor.description
    if description is None:
        raise DatabaseError("Database query did not return column metadata.")
    return [column[0] for column in description]


def _cursor_to_dicts(cursor: Cursor) -> list[dict[str, Any]]:
    """Convert all cursor rows to column-name-keyed dicts."""
    columns = _cursor_columns(cursor)
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _inserted_row_id(cursor: Cursor) -> int:
    """Require a generated row ID before committing an insert."""
    lastrowid = cursor.lastrowid
    if lastrowid is None:
        raise DatabaseError("Database insert did not return a row ID.")
    return lastrowid


def read_query(sql: str, sql_params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Execute a SELECT and return all rows as dicts."""
    logger.debug("SELECT %s | params=%s", sql, sql_params)
    conn = None
    cursor = None
    try:
        conn = _get_connection(_get_db_config())
        cursor = conn.cursor()
        cursor.execute(sql, sql_params)
        return _cursor_to_dicts(cursor)
    except Exception as exc:
        logger.exception("Database read failed")
        raise DatabaseError(f"Database read failed ({exc.__class__.__name__}): {exc}") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()



def read_query_one(sql: str, sql_params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    """Execute a SELECT and return the first row as a dict, or None."""
    logger.debug("SELECT (one) %s | params=%s", sql, sql_params)
    conn = None
    cursor = None
    try:
        conn = _get_connection(_get_db_config())
        cursor = conn.cursor()
        cursor.execute(sql, sql_params)
        columns = _cursor_columns(cursor)
        row = cursor.fetchone()
        return dict(zip(columns, row, strict=True)) if row else None
    except Exception as exc:
        logger.exception("Database read failed")
        raise DatabaseError(f"Database read failed ({exc.__class__.__name__}): {exc}") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()



def insert_query(sql: str, sql_params: tuple[Any, ...] = ()) -> int:
    """Execute an INSERT and return the new row's id."""
    logger.debug("INSERT %s | params=%s", sql, sql_params)
    conn = None
    cursor = None
    try:
        conn = _get_connection(_get_db_config())
        cursor = conn.cursor()
        cursor.execute(sql, sql_params)
        lastrowid = _inserted_row_id(cursor)
        conn.commit()
    except Exception as exc:
        if conn is not None:
            conn.rollback()
        logger.exception("Database insert failed")
        raise DatabaseError(f"Database insert failed ({exc.__class__.__name__}): {exc}") from exc
    else:
        return lastrowid
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def write_query(sql: str, sql_params: tuple[Any, ...] = ()) -> int:
    """Execute an UPDATE or DELETE and return the affected row count."""
    logger.debug("WRITE %s | params=%s", sql, sql_params)
    conn = None
    cursor = None
    try:
        conn = _get_connection(_get_db_config())
        cursor = conn.cursor()
        cursor.execute(sql, sql_params)
        conn.commit()
        return int(cursor.rowcount)
    except Exception as exc:
        if conn is not None:
            conn.rollback()
        logger.exception("Database write failed")
        raise DatabaseError(f"Database write failed ({exc.__class__.__name__}): {exc}") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()
